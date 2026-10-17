"""知识追踪：把平时小测、任务测评与代码实验证据合并成「掌握概率 + 置信度」。

口径说明（面向用户时可解释）：

- 每道答过的题算 1 次证据，答对记 1 分、答错记 0 分；
- 一次代码实验（三维评分）信息量更大，按 3 道题折算；
- 证据少时用平滑处理把分数拉向 50%，避免「做对 1 题就 100%」；
- 置信度 = 折算证据量 / (折算证据量 + 8)，证据越多越可信：
  < 30% 证据不足、< 60% 初步可信、其余 较可信；
- 掌握度分数仍可与原有 `knowledge_mastery` 三维评分对齐，不改数据库结构。
"""

import json
from datetime import datetime

from db import get_db

# 置信度曲线：折算证据量达到 8 次时置信度 50%
CONFIDENCE_K = 8.0
# 一次代码实验折算成多少道测评题
LAB_EVIDENCE_WEIGHT = 3
QUIZ_PRIOR_CORRECT = 1.0
QUIZ_PRIOR_TOTAL = 2.0


def _node_tags() -> set:
    """课程图谱里的知识点标签；非课程标签（如智能体分类）不进入追踪。"""
    try:
        from services import agent_course

        return {point["tag"] for point in agent_course.course_knowledge_points()}
    except Exception:
        return set()


def _name_to_tag() -> dict:
    """题库使用的中文知识点名 → 课程图谱 tag。"""
    try:
        from services import agent_course

        return {point["name"]: point["tag"] for point in agent_course.course_knowledge_points()}
    except Exception:
        return {}


def _normalize_tag(tag):
    """题库标注的是中文节点名，统一折算成图谱 tag。"""
    if not tag:
        return ""
    tag = str(tag).strip()
    return _name_to_tag().get(tag, tag)


def _parse_time(value):
    if not value:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).strip()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S.%f", "%Y-%m-%dT%H:%M:%S"):
        try:
            return datetime.strptime(text[:26], fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _loads(value, default):
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value or "")
    except (TypeError, ValueError):
        return default


def quiz_evidence(user_id: int, tags: set = None) -> dict:
    """从 quiz_sessions.answers_json 聚合每道题的作答证据。"""
    tags = tags if tags is not None else _node_tags()
    evidence = {}
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT id, answers_json, completed_at, created_at
               FROM quiz_sessions
               WHERE user_id = ? AND status = 'completed'""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        answers = _loads(row["answers_json"], [])
        if not isinstance(answers, list):
            continue
        stamp = _parse_time(row["completed_at"] or row["created_at"])
        for answer in answers:
            if not isinstance(answer, dict):
                continue
            tag = _normalize_tag(answer.get("knowledge_tag"))
            if not tag or (tags and tag not in tags):
                continue
            bucket = evidence.setdefault(tag, {
                "attempts": 0,
                "correct": 0,
                "score_sum": 0.0,
                "last_at": None,
            })
            bucket["attempts"] += 1
            if answer.get("is_correct"):
                bucket["correct"] += 1
            full = answer.get("full_score") or 100.0
            score = answer.get("score")
            if score is None:
                bucket["score_sum"] += 1.0 if answer.get("is_correct") else 0.0
            else:
                try:
                    bucket["score_sum"] += max(0.0, min(float(score) / float(full), 1.0))
                except (TypeError, ValueError, ZeroDivisionError):
                    bucket["score_sum"] += 1.0 if answer.get("is_correct") else 0.0
            if stamp and (bucket["last_at"] is None or stamp > bucket["last_at"]):
                bucket["last_at"] = stamp
    return evidence


def lab_evidence(user_id: int, tags: set = None) -> dict:
    """读取 knowledge_mastery 里的代码实验三维评分证据。"""
    tags = tags if tags is not None else _node_tags()
    evidence = {}
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT knowledge_tag, mastery_score, attempt_count, last_activity_at, updated_at
               FROM knowledge_mastery WHERE user_id = ?""",
            (user_id,),
        ).fetchall()
    finally:
        conn.close()

    for row in rows:
        tag = row["knowledge_tag"]
        if tags and tag not in tags:
            continue
        attempts = int(row["attempt_count"] or 0)
        score = float(row["mastery_score"] or 0)
        if attempts <= 0 and score <= 0:
            continue
        evidence[tag] = {
            "attempts": max(attempts, 1),
            "score": max(0.0, min(score, 1.0)),
            "last_at": _parse_time(row["last_activity_at"] or row["updated_at"]),
        }
    return evidence


def _confidence_label(confidence: float) -> str:
    if confidence < 0.3:
        return "证据不足"
    if confidence < 0.6:
        return "初步可信"
    return "较可信"


def mastery_profile(user_id: int, tags: set = None) -> dict:
    """每个知识点的掌握画像：分数、置信度、证据次数与来源。"""
    tags = tags if tags is not None else _node_tags()
    quizzes = quiz_evidence(user_id, tags)
    labs = lab_evidence(user_id, tags)

    profile = {}
    for tag in set(quizzes) | set(labs):
        quiz = quizzes.get(tag) or {}
        lab = labs.get(tag) or {}

        quiz_attempts = int(quiz.get("attempts") or 0)
        quiz_score = (
            (float(quiz.get("score_sum") or 0) + QUIZ_PRIOR_CORRECT)
            / (quiz_attempts + QUIZ_PRIOR_TOTAL)
            if quiz_attempts
            else None
        )
        lab_attempts = int(lab.get("attempts") or 0)
        lab_score = lab.get("score")

        quiz_weight = float(quiz_attempts)
        lab_weight = float(lab_attempts) * LAB_EVIDENCE_WEIGHT
        total_weight = quiz_weight + lab_weight

        if total_weight <= 0:
            continue
        if quiz_score is None:
            score = lab_score
        elif lab_score is None:
            score = quiz_score
        else:
            score = (quiz_score * quiz_weight + lab_score * lab_weight) / total_weight

        confidence = round(total_weight / (total_weight + CONFIDENCE_K), 3)
        last_at = max(
            [item for item in (quiz.get("last_at"), lab.get("last_at")) if item],
            default=None,
        )
        sources = []
        if quiz_attempts:
            sources.append("测评")
        if lab_attempts:
            sources.append("实验")

        profile[tag] = {
            "score": round(float(score), 3),
            "confidence": confidence,
            "confidence_label": _confidence_label(confidence),
            "evidence_count": quiz_attempts + lab_attempts,
            "quiz_attempts": quiz_attempts,
            "quiz_correct": int(quiz.get("correct") or 0),
            "quiz_score": round(quiz_score, 3) if quiz_score is not None else None,
            "lab_attempts": lab_attempts,
            "lab_score": round(float(lab_score), 3) if lab_score is not None else None,
            "source": "+".join(sources),
            "last_activity_at": last_at.isoformat() if last_at else None,
        }
    return profile


def mastery_by_knowledge(user_id: int, tags: set = None) -> dict:
    """供路径编排使用的掌握度主口径：tag -> 0~1 分数。"""
    return {tag: item["score"] for tag, item in mastery_profile(user_id, tags).items()}


def mastery_detail_by_knowledge(user_id: int, tags: set = None) -> dict:
    """兼容原有明细口径：tag -> {score, last_activity_at}，附带证据字段。"""
    return mastery_profile(user_id, tags)
