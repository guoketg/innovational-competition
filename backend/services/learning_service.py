"""伴随式学习服务"""
import json
from datetime import datetime
from services.ai_service import call_llm, extract_json_object, LEARNING_PATH_PROMPT
from services.diagnosis_service import get_user_knowledge_profile, get_all_tags_flat, generate_quiz
from services.question_bank_service import KNOWLEDGE_CATEGORY_MAP
from database import get_db, json_load

async def generate_learning_path(user_id: int, goal: str = "", timeline: str = "", learning_depth: str = "标准", diagnostic_session_id: int = None, modules: list = None) -> dict:
    """生成个性化学习路径
    Args:
        diagnostic_session_id: 可选，诊断测试的 session ID。
        modules: 可选，用户选中的模块名列表（如 ["智能体基础通识", "大模型与提示词工程"]）。
                 当提供时，从对应模块知识中直接构建路径，不调用LLM。
    """
    # ===== 模块选择模式：直接从知识结构构建学习路径 =====
    if modules and len(modules) > 0:
        from services.agent_course import TRACK_NAMES, plan_course_path

        # 新版项目制课程使用固定依赖顺序与显式实验绑定，不再从知识标签中随机拼装。
        # 生成前先判定学生水平，再按 skip / reorder / depth 三件事做个性化编排。
        if any(module in TRACK_NAMES for module in modules):
            selected = [name for name in TRACK_NAMES if name in modules]
            if not selected:
                raise ValueError("请选择至少一个 Agent 实战阶段")
            level_profile = _build_level_profile(user_id, diagnostic_session_id)
            return await _save_learning_path(
                user_id,
                plan_course_path(selected, level_profile, learning_depth),
            )

        import os as _os
        # 模块名 → 分类名映射
        MODULE_CATEGORY_MAP = {
            "智能体基础通识": "智能体基础概念",
            "大模型与提示词工程": ["大模型基座原理", "提示词工程"],
            "智能体四大核心能力模块": ["智能体框架开发", "智能体算法逻辑"],
            "开发框架与工程实践": "智能体框架开发",
            "多智能体系统": "多智能体应用",
            "评估安全与前沿拓展": "智能体算法逻辑",
        }

        from config import KNOWLEDGE_TAGS_PATH
        with open(KNOWLEDGE_TAGS_PATH, 'r', encoding='utf-8') as f:
            all_categories = json.load(f)

        # 收集选中模块对应的分类名
        target_categories = set()
        for mod in modules:
            cats = MODULE_CATEGORY_MAP.get(mod, [])
            if isinstance(cats, str):
                cats = [cats]
            target_categories.update(cats)

        # 从 knowledge_tags.json 中提取对应分类的知识点
        # 预加载学习资料索引，过滤掉无资料的标签
        materials_flat = {}
        materials_index_path = _os.path.join(
            _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
            "learning_materials", "index.json"
        )
        if _os.path.exists(materials_index_path):
            with open(materials_index_path, 'r', encoding='utf-8') as f:
                materials_index = json.load(f)
            for mod_name, items in materials_index.get("modules", {}).items():
                for tag_name, rel_path in items.items():
                    full = _os.path.join(
                        _os.path.dirname(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__)))),
                        "learning_materials", rel_path
                    )
                    if _os.path.exists(full):
                        materials_flat[tag_name] = rel_path

        phases = []
        day = 1
        for cat_data in all_categories:
            cat_name = cat_data["category"]
            if cat_name not in target_categories:
                continue
            tags = cat_data.get("tags", [])
            tasks = []
            for tag in tags[:12]:  # 每个分类最多12个任务
                knowledge = tag["name"]
                # 跳过没有对应学习资料的标签
                if knowledge not in materials_flat:
                    continue
                difficulty = tag.get("difficulty", "Lv2中等")
                # 根据难度推荐资源类型
                resource = "学习资源页面" if difficulty == "Lv1入门" else "动手实践" if difficulty == "Lv3高阶" else "理论+习题"
                tasks.append({
                    "day": day,
                    "topic": knowledge,
                    "knowledge": knowledge,
                    "action": f"学习「{knowledge}」核心概念与原理，完成相关练习",
                    "resource": resource,
                    "check": "理解核心定义并能用自己的话复述" if "入门" in difficulty else
                            "能独立解决相关练习题，准确率>70%" if "中等" in difficulty else
                            "能完成综合实践项目，解释底层原理"
                })
                day += 1

            if tasks:
                phases.append({
                    "name": cat_name,
                    "description": f"学习{cat_name}相关的核心知识点",
                    "tasks": tasks
                })

        # 构建完整路径数据
        path_data = {
            "phases": phases,
            "estimated_total_days": day - 1,
            "learning_depth": learning_depth,
            "weekly_goals": [
                "每天投入 45-60 分钟专注学习",
                "学完每个知识点后做 2-3 道练习巩固",
                "每周末花 30 分钟复习本周所学"
            ],
            "key_milestones": [p["name"] for p in phases],
            "tips": "按顺序学习效果最佳。遇到难理解的概念可使用「智能答疑」寻求帮助。",
            "modules_selected": modules
        }

        # 保存学习路径
        return await _save_learning_path(user_id, path_data)

    # ===== LLM生成模式（保留兼容，无模块选择时使用）=====
    profile = get_user_knowledge_profile(user_id)
    all_tags = get_all_tags_flat()

    # 获取用户信息
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()

    student_profile = {
        "learning_stage": user["learning_stage"] if user else "入门",
        "weak_points": profile["weak_points"],
        "strong_points": profile["strong_points"],
        "mastery": {k: round(v, 2) for k, v in list(profile["mastery"].items())[:10]}
    }

    # 如果有诊断测试结果，计算掌握等级并注入到学生画像中
    diagnostic_info = {}
    if diagnostic_session_id:
        diagnostic_info = _get_diagnostic_result(user_id, diagnostic_session_id)
        student_profile["diagnostic_mastery_level"] = diagnostic_info.get("mastery_level", "有一定基础")
        student_profile["diagnostic_correct_rate"] = diagnostic_info.get("correct_rate", 0)
        student_profile["diagnostic_note"] = diagnostic_info.get("note", "")

    # 构建知识体系描述和依赖链（精简版：只传必要数据）
    import os
    from config import KNOWLEDGE_TAGS_PATH
    with open(KNOWLEDGE_TAGS_PATH, 'r', encoding='utf-8') as f:
        categories = json.load(f)

    # 知识体系：只保留分类名和标签名，去掉冗余字段
    knowledge_system = [
        {"category": c["category"], "tags": [t["name"] for t in c["tags"]]}
        for c in categories
    ]

    # 前置依赖链：精简为一行表达式，去掉冗余文字
    prereq_parts = []
    for c in categories:
        if c.get("prerequisites"):
            for p in c["prerequisites"]:
                prereq_parts.append(f"{p}→{c['category']}")
        for t in c["tags"]:
            if t.get("prerequisites"):
                for p in t["prerequisites"]:
                    prereq_parts.append(f"{p}→{t['name']}")
    prerequisite_chain = "、".join(prereq_parts) if prereq_parts else "无特殊依赖"

    # 转义花括号
    def _escape(s):
        return s.replace('{', '{{').replace('}', '}}')

    student_profile_str = _escape(json.dumps(student_profile, ensure_ascii=False))
    knowledge_system_str = _escape(json.dumps(knowledge_system, ensure_ascii=False))
    prereq_escaped = _escape(prerequisite_chain)

    prompt = LEARNING_PATH_PROMPT.format(
        student_profile=student_profile_str,
        goal=goal or (user["learning_goal"] if user and user["learning_goal"] else "系统掌握AI智能体学科知识"),
        timeline=timeline or "2周",
        learning_depth=learning_depth,
        knowledge_system=knowledge_system_str,
        prerequisite_chain=prereq_escaped
    )

    # 学习路径生成使用更长超时（180s）和更大 max_tokens（容纳长JSON）
    # 个性化出口（#34）：LLM 调用注入完整画像（与 QA #22 / 教程 #26 同一主口径），异常回退基础提示
    base_system = "你是AI智能体学科的学习规划师，只输出JSON。"
    try:
        from services.personalization_service import build_personalized_system_prompt
        system_prompt = build_personalized_system_prompt(
            user_id,
            goal or (user["learning_goal"] if user and user["learning_goal"] else "学习路径规划"),
            base_system,
        )
    except Exception:
        system_prompt = base_system
    response = await call_llm(user_id, [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": prompt}
    ], temperature=0.7, max_tokens=4096)

    # 检查 LLM 调用是否返回了错误
    if response.startswith("LLM调用异常:") or response.startswith("LLM调用异常："):
        error_detail = response.replace("LLM调用异常:", "").replace("LLM调用异常：", "").strip()
        raise ValueError(f"AI模型调用失败: {error_detail}")

    path_data = extract_json_object(response)

    # 验证 path_data 必须包含 phases，否则说明 LLM 返回了无效内容
    if not path_data.get("phases"):
        raise ValueError(
            "AI模型未能生成有效的学习路径（缺少phases结构）。"
            "请检查：\n"
            "1. API Key 和 Base URL 是否匹配（如 DeepSeek 模型需搭配 DeepSeek 的 API 地址）\n"
            "2. 模型是否可用，API 账户余额是否充足\n"
            "3. 可前往「个人中心 → AI大模型配置」重新配置后重试"
        )

    # 保存学习深度到路径数据
    path_data["learning_depth"] = learning_depth

    # 【修复】后处理：重新分配连续的天数编号，确保LLM生成的任务天数顺序正确
    day_counter = 0
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            day_counter += 1
            task["day"] = day_counter
    # 更新预计总天数
    path_data["estimated_total_days"] = day_counter

    # 保存学习路径
    return await _save_learning_path(user_id, path_data)


async def _save_learning_path(user_id: int, path_data: dict) -> dict:
    """保存学习路径到数据库（公共方法，模块模式和LLM模式共用）"""
    conn = get_db()
    existing = conn.execute(
        "SELECT id FROM learning_paths WHERE user_id = ? AND status = 'active'",
        (user_id,)
    ).fetchone()

    path_json = json.dumps(path_data, ensure_ascii=False)
    progress_json = json.dumps({"completed_tasks": {}, "overall_progress": 0, "current_day": 1}, ensure_ascii=False)

    if existing:
        conn.execute(
            "UPDATE learning_paths SET path_data_json = ?, updated_at = ? WHERE id = ?",
            (path_json, datetime.now().isoformat(), existing["id"])
        )
    else:
        conn.execute(
            "INSERT INTO learning_paths (user_id, path_data_json, progress_json) VALUES (?, ?, ?)",
            (user_id, path_json, progress_json)
        )

    conn.commit()
    conn.close()
    return path_data


def map_goal_to_knowledge_categories(goal: str) -> list:
    """从用户输入的学习目标中提取关键词，映射到知识分类

    Examples:
        "2周学会RAG" → ["智能体框架开发"]
        "掌握多Agent协作" → ["多智能体应用"]
        "学习Transformer和大模型" → ["大模型基座原理"]
    """
    if not goal:
        return []

    # 按优先级排序的关键词（长的优先匹配，避免"大模型"误匹配"模型"）
    keywords_sorted = sorted(KNOWLEDGE_CATEGORY_MAP.keys(), key=len, reverse=True)

    matched_categories = []
    seen_categories = set()

    for keyword in keywords_sorted:
        if keyword.lower() in goal.lower():
            category = KNOWLEDGE_CATEGORY_MAP[keyword]
            if category not in seen_categories:
                matched_categories.append(category)
                seen_categories.add(category)

    # 如果没匹配到任何分类，返回所有分类（让诊断覆盖全面）
    if not matched_categories:
        matched_categories = list(set(KNOWLEDGE_CATEGORY_MAP.values()))

    return matched_categories


def _get_diagnostic_result(user_id: int, session_id: int) -> dict:
    """从诊断测试 session 中计算用户掌握等级

    Returns:
        {"mastery_level": "基础薄弱"|"有一定基础"|"较为熟练",
         "correct_rate": "67%",
         "correct_count": 6, "total_count": 10,
         "note": "..."}
    """
    conn = get_db()
    session = conn.execute(
        "SELECT * FROM quiz_sessions WHERE id = ? AND user_id = ?",
        (session_id, user_id)
    ).fetchone()

    if not session:
        conn.close()
        return {"mastery_level": "有一定基础", "correct_rate": "N/A", "note": "未找到诊断记录，使用默认等级"}

    # 解析答题记录
    answers_json = session["answers_json"] if session["answers_json"] else "[]"
    try:
        answers = json_load(answers_json)
    except (json.JSONDecodeError, TypeError):
        answers = []

    total = len(answers)
    if total == 0:
        conn.close()
        return {"mastery_level": "有一定基础", "correct_rate": "N/A", "note": "诊断测试无答题记录"}

    correct = sum(1 for a in answers if a.get("is_correct", False))
    correct_rate = correct / total

    if correct_rate < 0.4:
        mastery_level = "基础薄弱"
        note = "诊断测试正确率较低，该学生对目标知识领域的基础概念掌握不够扎实，建议从基础概念和入门实践开始学习"
    elif correct_rate <= 0.7:
        mastery_level = "有一定基础"
        note = "诊断测试正确率中等，该学生对目标知识领域有一定了解但存在知识盲区，建议理论+实践并重进行系统学习"
    else:
        mastery_level = "较为熟练"
        note = "诊断测试正确率较高，该学生对目标知识领域已有较好的掌握，建议侧重进阶内容、源码分析和实战项目"

    conn.close()

    return {
        "mastery_level": mastery_level,
        "correct_rate": f"{int(correct_rate * 100)}%",
        "correct_count": correct,
        "total_count": total,
        "note": note
    }


def _diagnostic_tag_scores(user_id: int, session_id: int) -> dict:
    """从诊断答题记录中按知识点统计正确率（0~1）。"""
    conn = get_db()
    try:
        session = conn.execute(
            "SELECT answers_json FROM quiz_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id)
        ).fetchone()
    finally:
        conn.close()

    if not session or not session["answers_json"]:
        return {}
    try:
        answers = json_load(session["answers_json"])
    except (json.JSONDecodeError, TypeError):
        return {}

    buckets = {}
    for answer in answers:
        tag = answer.get("knowledge_tag")
        if not tag:
            continue
        buckets.setdefault(tag, []).append(1.0 if answer.get("is_correct") else 0.0)
    return {tag: sum(values) / len(values) for tag, values in buckets.items() if values}


def _build_level_profile(user_id: int, diagnostic_session_id: int = None) -> dict:
    """判定学生起点，优先级：诊断结果 > 历史掌握度证据 > 注册信息。

    返回的 level_profile 会随路径一起保存，供后续漂移重编排使用。
    """
    from services.agent_course import COURSE_TRACKS, LEVEL_LABELS

    course_tags = {
        task.get("knowledge")
        for track in COURSE_TRACKS
        for task in track["tasks"]
        if task.get("knowledge")
    }

    try:
        historical_mastery = _mastery_by_knowledge(user_id)
    except Exception:
        historical_mastery = {}

    # 1) 有诊断结果：优先使用，置信度高
    if diagnostic_session_id:
        result = _get_diagnostic_result(user_id, diagnostic_session_id)
        if (result.get("total_count") or 0) > 0:
            level_map = {
                "基础薄弱": "beginner",
                "有一定基础": "intermediate",
                "较为熟练": "advanced",
            }
            level = level_map.get(result.get("mastery_level"), "intermediate")
            tag_scores = _diagnostic_tag_scores(user_id, diagnostic_session_id)
            merged = {**historical_mastery, **tag_scores}
            mastery = {tag: score for tag, score in merged.items() if tag in course_tags}
            weak_tags = [tag for tag, score in mastery.items() if score < 0.4]
            mastered_tags = [tag for tag, score in mastery.items() if score >= 0.7]
            rate_text = result.get("correct_rate")
            try:
                correct_rate = float(str(rate_text).replace("%", "")) / 100.0
            except (TypeError, ValueError):
                correct_rate = None
            return {
                "level": level,
                "level_label": LEVEL_LABELS[level],
                "confidence": "high",
                "source": "diagnostic",
                "correct_rate": correct_rate,
                "weak_tags": weak_tags,
                "mastered_tags": mastered_tags,
                "mastery": mastery,
                "note": result.get("note", ""),
            }

    # 2) 没有诊断：课程相关知识点积累到 3 条以上掌握度证据时，按平均掌握度判断
    evidence = {tag: score for tag, score in historical_mastery.items() if tag in course_tags}
    if len(evidence) >= 3:
        average = sum(evidence.values()) / len(evidence)
        if average < 0.4:
            level = "beginner"
        elif average <= 0.7:
            level = "intermediate"
        else:
            level = "advanced"
        weak_tags = [tag for tag, score in evidence.items() if score < 0.4]
        mastered_tags = [tag for tag, score in evidence.items() if score >= 0.7]
        return {
            "level": level,
            "level_label": LEVEL_LABELS[level],
            "confidence": "medium",
            "source": "mastery",
            "correct_rate": None,
            "weak_tags": weak_tags,
            "mastered_tags": mastered_tags,
            "mastery": evidence,
            "note": f"根据 {len(evidence)} 个知识点的练习记录估算，平均掌握度 {round(average * 100)}%",
        }

    # 3) 兜底：只用注册时填写的学习阶段，置信度低，后续由练习证据自动校正
    conn = get_db()
    try:
        user = conn.execute("SELECT learning_stage FROM users WHERE id = ?", (user_id,)).fetchone()
    finally:
        conn.close()
    stage = (user["learning_stage"] if user else "") or "入门"
    level = {"入门": "beginner", "进阶": "intermediate", "高阶": "advanced"}.get(stage, "beginner")
    return {
        "level": level,
        "level_label": LEVEL_LABELS[level],
        "confidence": "low",
        "source": "profile",
        "correct_rate": None,
        "weak_tags": [],
        "mastered_tags": [],
        "mastery": {},
        "note": f"按注册信息「{stage}」估算，做完练习后会自动校正",
    }


async def generate_diagnostic_test(user_id: int, goal: str = "", count: int = 10) -> dict:
    """根据用户的学习目标生成诊断测试卷

    1. 从 goal 中提取知识分类
    2. 从题库中选取相关题目
    3. 创建 quiz session 并返回
    """
    # 映射目标到知识分类
    focus_knowledge = map_goal_to_knowledge_categories(goal)

    # 根据用户掌握程度选择合适难度阶段
    profile = get_user_knowledge_profile(user_id)
    weak_count = len(profile.get("weak_points", []))
    if weak_count >= 3:
        stage = "入门"
    elif weak_count >= 1:
        stage = "进阶"
    else:
        stage = "进阶"  # 默认进阶，有一定区分度

    # 调用 diagnosis_service 生成题目
    result = await generate_quiz(
        user_id=user_id,
        stage=stage,
        count=count,
        focus_knowledge=focus_knowledge if focus_knowledge else None,
        use_timer=False
    )

    # 添加诊断元信息
    result["diagnostic_goal"] = goal
    result["diagnostic_categories"] = focus_knowledge

    return result


def _load_quick_quiz_questions() -> list:
    """读取 5 道快速测评题；题库缺失时返回空列表。"""
    import os

    path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "quick_quiz_dsa.json",
    )
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("questions", []) or []
    except (OSError, json.JSONDecodeError):
        return []


def start_quick_quiz(user_id: int) -> dict:
    """开始 5 道快速测评：题目带课程知识点标签，提交后才能用于个性化编排。"""
    questions = _load_quick_quiz_questions()
    if not questions:
        raise ValueError("快速测评题库为空，请检查 data/quick_quiz_dsa.json")

    conn = get_db()
    try:
        cursor = conn.execute(
            "INSERT INTO quiz_sessions (user_id, stage, questions_json, status) VALUES (?, ?, ?, 'pending')",
            (user_id, "入门", json.dumps(questions, ensure_ascii=False)),
        )
        session_id = cursor.lastrowid
        conn.execute(
            "INSERT INTO learning_records (user_id, knowledge_tag, action_type, result_json) VALUES (?, ?, 'quiz_start', ?)",
            (user_id, "综合", json.dumps({"session_id": session_id, "count": len(questions), "quick": True}, ensure_ascii=False)),
        )
        conn.commit()
    finally:
        conn.close()

    # 返回给前端时去掉答案与解析，避免先看到结果。
    public_questions = [
        {key: value for key, value in question.items() if key not in ("answer", "analysis")}
        for question in questions
    ]
    return {"session_id": session_id, "questions": public_questions, "total": len(public_questions)}


def _is_quick_quiz_correct(expected: str, actual: str, question_type: str) -> bool:
    """判断题干答案是否正确；多选按集合比较，其余按去空格后的整串比较。"""
    expected = (expected or "").strip()
    actual = (actual or "").strip()
    if not actual:
        return False
    if question_type == "多选":
        expected_set = {item.strip() for item in expected.split(",") if item.strip()}
        actual_set = {item.strip() for item in actual.split(",") if item.strip()}
        return expected_set == actual_set
    return actual == expected


def submit_quick_quiz(user_id: int, session_id: int, answers: list) -> dict:
    """批改快速测评并把每题的知识点得分写入 answers_json，供路径编排读取。"""
    conn = get_db()
    try:
        session = conn.execute(
            "SELECT * FROM quiz_sessions WHERE id = ? AND user_id = ?",
            (session_id, user_id),
        ).fetchone()
        if not session:
            raise ValueError("测评会话不存在")

        questions = json_load(session["questions_json"]) or []
        answer_map = {
            answer.get("question_id"): answer.get("user_answer", "")
            for answer in (answers or [])
        }

        details = []
        knowledge_analysis = {}
        correct_count = 0

        for question in questions:
            question_id = question.get("question_id")
            user_answer = str(answer_map.get(question_id, "") or "").strip()
            question_type = question.get("question_type", "")
            is_correct = _is_quick_quiz_correct(question.get("answer", ""), user_answer, question_type)
            if is_correct:
                correct_count += 1

            tag = question.get("knowledge_tag") or "综合"
            bucket = knowledge_analysis.setdefault(tag, {"correct": 0, "total": 0})
            bucket["total"] += 1
            if is_correct:
                bucket["correct"] += 1

            details.append({
                "question_id": question_id,
                "question": question.get("question", ""),
                "question_type": question_type,
                "options": question.get("options", []),
                "user_answer": user_answer or "(未作答)",
                "correct_answer": question.get("answer", ""),
                "is_correct": is_correct,
                "knowledge_tag": tag,
                "knowledge_point": question.get("knowledge_point", ""),
                "difficulty": question.get("difficulty", ""),
                "analysis": question.get("analysis", ""),
            })

        total = len(questions)
        correct_rate = round(correct_count / total, 4) if total else 0.0
        for bucket in knowledge_analysis.values():
            bucket["mastery"] = round(bucket["correct"] / bucket["total"], 2) if bucket["total"] else 0.5

        report = {
            "correct_rate": correct_rate,
            "correct_count": correct_count,
            "total_count": total,
            "knowledge_analysis": knowledge_analysis,
            "summary": f"快速测评答对 {correct_count}/{total} 题，路线会按各知识点的对错调整。",
        }

        conn.execute(
            "UPDATE quiz_sessions SET answers_json = ?, score = ?, total = ?, report_json = ?, status = 'completed', completed_at = ? WHERE id = ? AND user_id = ?",
            (
                json.dumps(details, ensure_ascii=False),
                correct_count,
                total,
                json.dumps(report, ensure_ascii=False),
                datetime.now().isoformat(),
                session_id,
                user_id,
            ),
        )
        for detail in details:
            conn.execute(
                "INSERT INTO learning_records (user_id, knowledge_tag, action_type, result_json) VALUES (?, ?, 'quiz', ?)",
                (
                    user_id,
                    detail["knowledge_tag"],
                    json.dumps({
                        "session_id": session_id,
                        "question_id": detail["question_id"],
                        "is_correct": detail["is_correct"],
                        "quick": True,
                    }, ensure_ascii=False),
                ),
            )
        conn.commit()
    finally:
        conn.close()

    return {
        "session_id": session_id,
        "score": correct_count,
        "total": total,
        "correct_rate": correct_rate,
        "details": details,
        "report": report,
    }


async def delete_learning_path(user_id: int) -> dict:
    """删除用户当前的活跃学习路径"""
    conn = get_db()
    cursor = conn.execute(
        "DELETE FROM learning_paths WHERE user_id = ? AND status = 'active'",
        (user_id,)
    )
    deleted = cursor.rowcount
    conn.commit()
    conn.close()
    return {"deleted": deleted, "message": "学习路径已删除" if deleted else "没有可删除的学习路径"}


async def get_learning_path(user_id: int) -> dict:
    """获取当前学习路径"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    conn.close()

    if not row:
        return {}

    path_data = json_load(row["path_data_json"]) if row["path_data_json"] else {}
    progress = json_load(row["progress_json"]) if row["progress_json"] else {}

    # 课程方向已从概念题库切换为项目制 Agent 工程。旧任务无法可靠映射到新实验，
    # 因此首次读取时执行一次显式版本迁移，保留路径记录但重置任务进度。
    # v1 是旧的固定骨架，原地升级为 v2 并保留进度；v2 已是按水平编排的结果，原样使用。
    from services.agent_course import (
        CURRICULUM_VERSION,
        CURRICULUM_VERSION_V1,
        DEPTH_LEVELS,
        TRACK_NAMES,
        plan_course_path,
    )

    curriculum_version = path_data.get("curriculum_version")
    if curriculum_version == CURRICULUM_VERSION_V1:
        depth = path_data.get("learning_depth", "标准")
        depth_level = DEPTH_LEVELS.get(depth, depth)
        for phase in path_data.get("phases", []):
            for task in phase.get("tasks", []):
                task.setdefault("depth_level", depth_level)
                task.setdefault("skippable", False)
        path_data["curriculum_version"] = CURRICULUM_VERSION
        path_data["depth_level"] = depth_level
        path_data.setdefault("level_profile", {
            "level": "intermediate",
            "level_label": "有一定基础",
            "confidence": "low",
            "source": "legacy",
            "correct_rate": None,
            "weak_tags": [],
            "mastered_tags": [],
            "mastery": {},
            "note": "旧版固定骨架，未做个性化编排",
        })
        path_data.setdefault("applied_operators", {
            "skip": {"applied": False, "count": 0, "topics": []},
            "reorder": {"applied": False, "phase_count": 0},
            "depth": {"level": depth_level},
        })
        path_data.setdefault(
            "personalization_summary",
            "这条路线是早期生成的固定骨架，还没有按你的水平调整；点「重新生成」即可获得个性化版本。",
        )
        conn_upgrade = get_db()
        conn_upgrade.execute(
            "UPDATE learning_paths SET path_data_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(path_data, ensure_ascii=False), datetime.now().isoformat(), row["id"]),
        )
        conn_upgrade.commit()
        conn_upgrade.close()

    elif curriculum_version != CURRICULUM_VERSION:
        path_data = plan_course_path(
            TRACK_NAMES,
            {
                "level": "intermediate",
                "level_label": "有一定基础",
                "confidence": "low",
                "source": "legacy",
                "correct_rate": None,
                "weak_tags": [],
                "mastered_tags": [],
                "mastery": {},
                "note": "旧版路径无法映射到新课程，已重建",
            },
            path_data.get("learning_depth", "标准"),
        )
        path_data["migrated_from_legacy"] = True
        progress = {
            "completed_tasks": {},
            "overall_progress": 0,
            "current_day": 1,
            "remedial_tasks": {},
        }
        conn_migration = get_db()
        conn_migration.execute(
            "UPDATE learning_paths SET path_data_json = ?, progress_json = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(path_data, ensure_ascii=False),
                json.dumps(progress, ensure_ascii=False),
                datetime.now().isoformat(),
                row["id"],
            ),
        )
        conn_migration.commit()
        conn_migration.close()

    original_ct = progress.get("completed_tasks", [])
    progress = _normalize_progress(progress)

    # 如果发生了格式迁移（旧列表→新对象），持久化到DB
    if isinstance(original_ct, list) and original_ct:
        conn2 = get_db()
        conn2.execute(
            "UPDATE learning_paths SET progress_json = ? WHERE id = ?",
            (json.dumps(progress, ensure_ascii=False), row["id"])
        )
        conn2.commit()
        conn2.close()

    # 【迁移】修复旧路径中所有任务 day=1 的问题：重新分配连续天数
    # 同时重建 progress 中的 key，确保与新的 day 编号一致
    if path_data.get("phases"):
        all_days = []
        for phase in path_data["phases"]:
            for task in phase.get("tasks", []):
                all_days.append(task.get("day", 1))
        # 如果路径有多个任务且全部 day 都是 1，则需要修复
        if len(all_days) > 1 and all(d == 1 for d in all_days):
            # Step 1: 建立 topic → new_day 映射
            topic_to_new_day = {}
            day_counter = 0
            for phase in path_data["phases"]:
                for task in phase.get("tasks", []):
                    day_counter += 1
                    task["day"] = day_counter
                    topic_to_new_day[task["topic"]] = day_counter
            path_data["estimated_total_days"] = day_counter

            # Step 2: 重建 progress 中的 completed_tasks key
            # 旧 key 格式 "1-{topic}" → 新 key "{new_day}-{topic}"
            ct = progress.get("completed_tasks", {})
            if isinstance(ct, dict) and ct:
                new_ct = {}
                for old_key, val in ct.items():
                    # 旧 key 格式: "1-{topic}"，提取 topic 部分
                    parts = old_key.split("-", 1)
                    topic = parts[1] if len(parts) > 1 else old_key
                    new_day = topic_to_new_day.get(topic, 1)
                    new_key = _get_task_key(new_day, topic)
                    new_ct[new_key] = val
                progress["completed_tasks"] = new_ct

            # Step 3: 持久化修复后的路径数据和进度
            conn_mig = get_db()
            conn_mig.execute(
                "UPDATE learning_paths SET path_data_json = ?, progress_json = ? WHERE id = ?",
                (json.dumps(path_data, ensure_ascii=False),
                 json.dumps(progress, ensure_ascii=False),
                 row["id"])
            )
            conn_mig.commit()
            conn_mig.close()

    # 将复习任务注入到对应 day 的任务列表前面
    remedial = progress.get("remedial_tasks", {})
    remedial_modified = False
    if remedial and path_data.get("phases"):
        for phase in path_data["phases"]:
            for task in phase.get("tasks", []):
                day = task.get("day", 0)
                day_key = str(day)
                if day_key in remedial and remedial[day_key]:
                    # 在 phase 的 tasks 中，在该 day 原有任务前面插入复习任务
                    # 找到该 day 的第一个 task 位置
                    insert_positions = {}
                    for i, t in enumerate(phase["tasks"]):
                        d = t.get("day", 0)
                        if d not in insert_positions:
                            insert_positions[d] = i
                    if day in insert_positions:
                        insert_at = insert_positions[day]
                        for r_task in reversed(remedial[day_key]):
                            phase["tasks"].insert(insert_at, r_task)
                    del remedial[day_key]  # 已注入，清除
                    remedial_modified = True
        if remedial_modified:
            progress["remedial_tasks"] = remedial
            # 持久化：同时保存修改后的 path_data（含已注入的复习任务）和 progress，
            # 避免刷新页面后复习任务消失
            conn3 = get_db()
            conn3.execute(
                "UPDATE learning_paths SET path_data_json = ?, progress_json = ? WHERE id = ?",
                (json.dumps(path_data, ensure_ascii=False),
                 json.dumps(progress, ensure_ascii=False),
                 row["id"])
            )
            conn3.commit()
            conn3.close()

    # 第二天起，根据编程实验的基本测试/用户解释/变式迁移证据，虚拟追加第 5 阶段。
    # 该阶段每次读取时动态生成，不写回基础课程，避免重复插入。
    try:
        from services.personalization_service import get_due_review_recommendations

        recommendations = get_due_review_recommendations(user_id)
        if recommendations:
            task_by_lab = {}
            for phase in path_data.get("phases", []):
                for task in phase.get("tasks", []):
                    if task.get("lab_id"):
                        task_by_lab[task["lab_id"]] = task
            review_tasks = []
            review_notices = []
            for item in recommendations:
                source = task_by_lab.get(item.get("source_exercise_id"))
                if not source:
                    continue
                mastery_percent = round(float(item.get("mastery_score", 0)) * 100)
                review_task = dict(source)
                review_task.update({
                    "topic": f"个性化复习：{item['knowledge_tag']}",
                    "knowledge": source.get("knowledge") or item["knowledge_tag"],
                    "action": f"系统检测到你对「{item['knowledge_tag']}」的熟悉程度较低，建议返回编程实验重点复习。",
                    "check": "重新通过基本测试、用自己的话解释关键实现，并完成变式迁移",
                    "personalized_review": True,
                    "mastery_score": item["mastery_score"],
                    "basic_score": item["basic_score"],
                    "explanation_score": item["explanation_score"],
                    "transfer_score": item["transfer_score"],
                    "source_topic": source.get("topic"),
                })
                review_tasks.append(review_task)
                review_notices.append({
                    "knowledge_tag": item["knowledge_tag"],
                    "mastery_percent": mastery_percent,
                    "lab_id": source.get("lab_id"),
                    "module_id": source.get("module_id"),
                    "topic": source.get("topic"),
                })
            if review_tasks:
                path_data["phases"].append({
                    "name": "个性化复习路径",
                    "description": "根据昨天及更早的实验能力证据动态生成",
                    "personalized_review": True,
                    "tasks": review_tasks,
                })
                path_data["personalized_review"] = {
                    "title": f"检测到 {len(review_tasks)} 个知识点需要返工",
                    "message": f"系统检测到你对「{review_tasks[0]['knowledge']}」的熟悉程度较低，建议先复习昨天的编程部分。",
                    "items": review_notices,
                }
    except Exception:
        pass

    return {
        "id": row["id"],
        "path_data": path_data,
        "progress": progress,
        "status": row["status"],
        "created_at": row["created_at"],
        "updated_at": row["updated_at"]
    }

# ===== 个性化学习路径：路线图·学习地图（技术方案.md §5.8 第一版）=====

_PREREQUISITES_FILENAME = "dsa_prerequisites.json"


def _load_prerequisites() -> dict:
    """读取 dsa 知识点先修依赖表（本地静态数据；读取失败时降级为空表）。"""
    import os

    path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", _PREREQUISITES_FILENAME)
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f).get("prerequisites", {}) or {}
    except Exception:
        return {}


def _mastery_by_knowledge(user_id: int) -> dict:
    """读取主口径 knowledge_mastery 表：knowledge_tag -> mastery_score。"""
    conn = get_db()
    try:
        rows = conn.execute(
            "SELECT knowledge_tag, mastery_score FROM knowledge_mastery WHERE user_id = ?",
            (user_id,)
        ).fetchall()
    finally:
        conn.close()
    return {r["knowledge_tag"]: float(r["mastery_score"] or 0) for r in rows}


def _mastery_band(score) -> str:
    """掌握度分档：≥0.7 可快进 / 0.4–0.7 在学 / <0.4 需补强 / 无数据。"""
    from services.teaching_policy_service import MASTERY_HIGH, MASTERY_LOW

    if score is None:
        return "unknown"
    if score >= MASTERY_HIGH:
        return "high"
    if score >= MASTERY_LOW:
        return "medium"
    return "low"


def _topological_tiers(stations: list, prereq_map: dict) -> dict:
    """按先修依赖做拓扑分层，tier = 从根节点出发的最长路径深度（即拓扑深度）。"""
    ids = {s.get("knowledge") for s in stations if s.get("knowledge")}
    memo = {}

    def depth(knowledge: str, seen: set) -> int:
        if knowledge in memo:
            return memo[knowledge]
        if knowledge in seen:  # 环保护：依赖表若出现环，回退为 0
            return 0
        parents = [p for p in prereq_map.get(knowledge, []) if p in ids]
        value = 0 if not parents else 1 + max(depth(p, seen | {knowledge}) for p in parents)
        memo[knowledge] = value
        return value

    for knowledge in ids:
        depth(knowledge, set())
    return memo


async def build_learning_roadmap(user_id: int) -> dict:
    """把当前学习路径投影成「路线图·学习地图」（§5.8 第一版）。

    节点 = 路径上的每一站（一次任务），带掌握度分档与三子项进度；
    边 = 知识点先修依赖（knowledge_tag ↔ data/dsa_prerequisites.json），
    箭头方向即拓扑序方向，分层层级 = 拓扑深度。
    每次读取时动态生成的「个性化复习路径」不计入地图，避免图形抖动。
    """
    from services.agent_course import TRACK_NAMES

    path = await get_learning_path(user_id)
    if not path:
        return {
            "has_path": False,
            "roadmap": None,
            "available_tracks": TRACK_NAMES,
        }

    path_data = path.get("path_data") or {}
    progress = path.get("progress") or {}
    completed_tasks = progress.get("completed_tasks", {}) or {}
    current_day = progress.get("current_day", 1)

    mastery_map = _mastery_by_knowledge(user_id)
    prereq_map = _load_prerequisites()

    # 1) 站点：路径上的每一次任务（排除动态生成的复习阶段）
    stations = []
    phases = []
    for phase in path_data.get("phases", []):
        if phase.get("personalized_review"):
            continue
        phase_index = len(phases)
        tasks = phase.get("tasks", [])
        phases.append({
            "index": phase_index,
            "name": phase.get("name", ""),
            "description": phase.get("description", ""),
            "total": len(tasks),
            "done": 0,
        })
        for task in tasks:
            day = task.get("day", 0)
            topic = task.get("topic", "")
            status_map = completed_tasks.get(_get_task_key(day, topic), {}) or {}
            knowledge = task.get("knowledge", "")
            mastery = mastery_map.get(knowledge) if knowledge else None
            stations.append({
                "key": _get_task_key(day, topic),
                "day": day,
                "topic": topic,
                "knowledge": knowledge,
                "lab_id": task.get("lab_id"),
                "module_id": task.get("module_id"),
                "duration": task.get("duration"),
                "phase_index": phase_index,
                "phase_name": phase.get("name", ""),
                "mastery": round(mastery, 3) if mastery is not None else None,
                "mastery_band": _mastery_band(mastery),
                "sub_tasks": {k: bool(status_map.get(k, False)) for k in ("learn", "quiz", "code")},
                "completed_count": _count_completed_sub_tasks(status_map),
                "is_remedial": bool(task.get("remedial")),
            })

    # 2) 拓扑分层 + 先修边（同一知识点的连续项目之间补顺序边，保证图连通）
    tiers = _topological_tiers(stations, prereq_map)
    by_knowledge = {}
    for station in stations:
        knowledge = station.get("knowledge")
        if not knowledge:
            continue
        station["tier"] = tiers.get(knowledge, 0)
        station["prerequisites"] = [p for p in prereq_map.get(knowledge, []) if p in tiers]
        by_knowledge.setdefault(knowledge, []).append(station)

    edges = []
    for knowledge, group in by_knowledge.items():
        group.sort(key=lambda s: s["day"])
        for prev, nxt in zip(group, group[1:]):
            edges.append({"source": prev["key"], "target": nxt["key"], "kind": "sequence"})
        first = group[0]
        for prereq in first["prerequisites"]:
            parents = by_knowledge.get(prereq) or []
            if not parents:
                continue
            last_parent = max(parents, key=lambda s: s["day"])
            if last_parent["key"] != first["key"]:
                edges.append({"source": last_parent["key"], "target": first["key"], "kind": "prereq"})

    # 3) 状态：done 全子项完成 / current 当前站 / locked 前置未完成 / todo
    done_knowledge = {
        knowledge for knowledge, group in by_knowledge.items()
        if all(s["completed_count"] >= 3 for s in group)
    }
    for station in stations:
        if station["completed_count"] >= 3:
            station["status"] = "done"
        elif station["day"] == current_day:
            station["status"] = "current"
        elif any(p not in done_knowledge for p in station["prerequisites"]):
            station["status"] = "locked"
        else:
            station["status"] = "todo"

    for phase in phases:
        group = [s for s in stations if s["phase_index"] == phase["index"]]
        phase["done"] = sum(1 for s in group if s["status"] == "done")

    total_stations = len(stations)
    completed_stations = sum(1 for s in stations if s["status"] == "done")
    current_station = next((s for s in stations if s["status"] == "current"), None) \
        or next((s for s in stations if s["status"] != "done"), None)

    return {
        "has_path": True,
        "curriculum_version": path_data.get("curriculum_version"),
        "learning_depth": path_data.get("learning_depth"),
        "updated_at": path.get("updated_at"),
        "summary": {
            "total_stations": total_stations,
            "completed_stations": completed_stations,
            "overall_progress": progress.get("overall_progress", 0),
            "current_day": current_day,
            "current_station_key": current_station["key"] if current_station else None,
            "current_station_topic": current_station["topic"] if current_station else None,
        },
        "phases": phases,
        "stations": stations,
        "edges": edges,
        "available_tracks": TRACK_NAMES,
        "review_notice": path_data.get("personalized_review"),
    }


def _normalize_progress(progress: dict) -> dict:
    """将旧版 completed_tasks 列表格式迁移为新的对象格式"""
    ct = progress.get("completed_tasks", [])
    if isinstance(ct, list):
        # 旧格式是简单列表，迁移时只标记learn为True（旧系统中"完成"主要指已学习）
        # quiz和code默认False，避免误标记
        new_ct = {}
        for item in ct:
            new_ct[item] = {"learn": True, "quiz": False, "code": False}
        progress["completed_tasks"] = new_ct
    # 确保每个任务值都是完整的字典，缺失子项默认False
    for key, val in list(progress.get("completed_tasks", {}).items()):
        if not isinstance(val, dict):
            progress["completed_tasks"][key] = {"learn": False, "quiz": False, "code": False}
        else:
            for sub in ["learn", "quiz", "code"]:
                if sub not in val:
                    val[sub] = False
    # 确保其他字段存在
    if "overall_progress" not in progress:
        progress["overall_progress"] = 0
    if "current_day" not in progress:
        progress["current_day"] = 1
    if "remedial_tasks" not in progress:
        progress["remedial_tasks"] = {}
    return progress


def _get_task_key(day: int, topic: str) -> str:
    return f"{day}-{topic}"


def _is_task_fully_complete(task_status: dict) -> bool:
    """检查任务是否三个子项全部完成"""
    return task_status.get("learn", False) and task_status.get("quiz", False) and task_status.get("code", False)


def _count_completed_sub_tasks(task_status: dict) -> int:
    """统计已完成的子任务数"""
    return sum(1 for k in ["learn", "quiz", "code"] if task_status.get(k, False))


def _check_and_advance_day(progress: dict, path_data: dict) -> bool:
    """检查当前 day 的所有任务是否全部完成，若是则推进 current_day"""
    current_day = progress.get("current_day", 1)
    completed_tasks = progress.get("completed_tasks", {})

    day_task_keys = []
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("day") == current_day:
                day_task_keys.append(_get_task_key(task["day"], task["topic"]))

    if day_task_keys and all(
        _is_task_fully_complete(completed_tasks.get(k, {})) for k in day_task_keys
    ):
        progress["current_day"] = current_day + 1
        return True
    return False


async def update_path_progress(user_id: int, task_key: str, completed: bool = True,
                                sub_action: str = None) -> dict:
    """更新学习路径进度

    Args:
        task_key: "{day}-{topic}"
        completed: True/False
        sub_action: "learn" | "quiz" | "code" | None (None=全标记)
    """
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not row:
        conn.close()
        return {"error": "没有活跃的学习路径"}

    progress = json_load(row["progress_json"]) if row["progress_json"] else {"completed_tasks": [], "overall_progress": 0, "current_day": 1, "remedial_tasks": {}}
    progress = _normalize_progress(progress)
    completed_tasks = progress["completed_tasks"]

    # 初始化任务状态
    if task_key not in completed_tasks:
        completed_tasks[task_key] = {"learn": False, "quiz": False, "code": False}

    task_status = completed_tasks[task_key]

    if sub_action:
        # 更新指定子动作
        task_status[sub_action] = completed
    else:
        # 兼容旧接口：全标记
        task_status["learn"] = completed
        task_status["quiz"] = completed
        task_status["code"] = completed

    # 计算整体进度
    path_data = json_load(row["path_data_json"]) if row["path_data_json"] else {}
    total_tasks = 0
    completed_count = 0
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            total_tasks += 1
            key = _get_task_key(task.get("day", 0), task.get("topic", ""))
            if _is_task_fully_complete(completed_tasks.get(key, {})):
                completed_count += 1

    progress["overall_progress"] = round(completed_count / total_tasks * 100) if total_tasks > 0 else 0
    progress["completed_tasks"] = completed_tasks

    # 检查是否当天所有任务全部完成，推进 current_day
    _check_and_advance_day(progress, path_data)

    conn.execute(
        "UPDATE learning_paths SET progress_json = ?, updated_at = ? WHERE id = ?",
        (json.dumps(progress, ensure_ascii=False), datetime.now().isoformat(), row["id"])
    )
    conn.commit()
    conn.close()

    return progress


async def record_quiz_result(user_id: int, task_day: int, correct_rate: float,
                              error_knowledge_tags: list = None) -> dict:
    """记录做题结果：正确率<60%时自动为下一天生成复习任务"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not row:
        conn.close()
        return {"error": "没有活跃的学习路径"}

    progress = json_load(row["progress_json"]) if row["progress_json"] else {}
    progress = _normalize_progress(progress)

    # 标记 quiz 子任务完成
    path_data = json_load(row["path_data_json"]) if row["path_data_json"] else {}
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("day") == task_day:
                task_key = _get_task_key(task_day, task["topic"])
                if task_key not in progress["completed_tasks"]:
                    progress["completed_tasks"][task_key] = {"learn": False, "quiz": False, "code": False}
                progress["completed_tasks"][task_key]["quiz"] = True

    # 正确率<60% → 生成复习任务，插入到 day+1
    if correct_rate < 0.6 and error_knowledge_tags:
        # 找到原始任务的知识点（学习资料索引中保证存在）
        original_knowledge = ""
        for phase in path_data.get("phases", []):
            for t in phase.get("tasks", []):
                if t.get("day") == task_day and not t.get("remedial"):
                    original_knowledge = t.get("knowledge", "")
                    break
            if original_knowledge:
                break
        review_knowledge = original_knowledge or error_knowledge_tags[0]

        next_day = task_day + 1
        remedial = progress.get("remedial_tasks", {})
        next_key = str(next_day)
        if next_key not in remedial:
            remedial[next_key] = []
        remedial[next_key].append({
            "day": next_day,
            "topic": f"复习：{review_knowledge}",
            "knowledge": review_knowledge,
            "action": f"针对性复习「{review_knowledge}」相关知识点，重做错题并理解错误原因",
            "resource": "错题本 + 学习资料",
            "check": "能独立正确解答该知识点的题目",
            "remedial": True,
            "source_day": task_day,
            "correct_rate": round(correct_rate * 100)
        })

        progress["remedial_tasks"] = remedial

    # 检查是否当天所有任务全部完成，推进 current_day
    _check_and_advance_day(progress, path_data)

    conn.execute(
        "UPDATE learning_paths SET progress_json = ? WHERE id = ?",
        (json.dumps(progress, ensure_ascii=False), row["id"])
    )
    conn.commit()
    conn.close()

    return progress


async def get_daily_tasks(user_id: int, date: str = None) -> dict:
    """获取每日任务"""
    if not date:
        date = datetime.now().strftime("%Y-%m-%d")

    conn = get_db()
    row = conn.execute(
        "SELECT * FROM daily_tasks WHERE user_id = ? AND date = ?",
        (user_id, date)
    ).fetchone()

    if not row:
        # 自动生成每日任务
        path = await get_learning_path(user_id)
        task_data = await generate_daily_tasks(user_id, path, date)
        conn.close()
        return {
            "id": None,
            "date": date,
            "tasks": task_data.get("tasks", []),
            "study_tips": task_data.get("study_tips", ""),
            "completed": False
        }

    conn.close()
    task_data = json_load(row["task_data_json"]) if row["task_data_json"] else {}
    return {
        "id": row["id"],
        "date": date,
        "tasks": task_data.get("tasks", []),
        "study_tips": task_data.get("study_tips", ""),
        "completed": bool(row["completed"])
    }

async def generate_daily_tasks(user_id: int, path: dict, date: str) -> dict:
    """生成每日任务"""
    path_data = path.get("path_data", {})
    progress = path.get("progress", {})
    completed_tasks = progress.get("completed_tasks", [])
    current_day = progress.get("current_day", 1)

    # 寻找当前日期的任务
    daily_tasks_data = []
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("day") == current_day:
                daily_tasks_data.append(task)

    if not daily_tasks_data:
        daily_tasks_data = [
            {"topic": "复习已学知识点", "knowledge": "综合复习", "action": "回顾本周错题和笔记", "resource": "错题本", "check": "完成错题回顾"},
            {"topic": "AI智能体概念巩固", "knowledge": "智能体基础概念", "action": "阅读教材相关内容，做好笔记", "resource": "教材/课件", "check": "能用自己的话解释核心概念"},
            {"topic": "每日一练", "knowledge": "综合练习", "action": "完成3-5道练习题", "resource": "在线题库", "check": "正确率>60%"}
        ]

    task_data = {
        "date": date,
        "tasks": daily_tasks_data,
        "study_tips": "每天保持专注学习30分钟以上，及时记录疑问便于答疑"
    }

    # 保存
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO daily_tasks (user_id, task_data_json, completed, date) VALUES (?, ?, 0, ?)",
        (user_id, json.dumps(task_data, ensure_ascii=False), date)
    )
    conn.commit()
    conn.close()

    return task_data

async def update_daily_task(user_id: int, date: str, completed: int = 1) -> dict:
    """更新每日任务完成状态，并同步到学习路径"""
    conn = get_db()
    conn.execute(
        "UPDATE daily_tasks SET completed = ? WHERE user_id = ? AND date = ?",
        (completed, user_id, date)
    )
    conn.commit()

    # 记录学习时长 + 推进学习天数
    if completed:
        existing = conn.execute(
            "SELECT * FROM learning_stats WHERE user_id = ? AND date = ?",
            (user_id, date)
        ).fetchone()
        if existing:
            conn.execute(
                "UPDATE learning_stats SET study_duration = study_duration + 30 WHERE user_id = ? AND date = ?",
                (user_id, date)
            )
        else:
            conn.execute(
                "INSERT INTO learning_stats (user_id, date, study_duration, questions_done, correct_rate, knowledge_mastery_json) VALUES (?, ?, 30, 0, 0, '{}')",
                (user_id, date)
            )
        conn.commit()

        # 同步：将当前 day 的所有路径任务标记为完成
        path_row = conn.execute(
            "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()

        if path_row:
            progress = json_load(path_row["progress_json"]) if path_row["progress_json"] else {}
            progress = _normalize_progress(progress)
            completed_tasks = progress.get("completed_tasks", {})
            current_day = progress.get("current_day", 1)

            path_data = json_load(path_row["path_data_json"]) if path_row["path_data_json"] else {}
            total_tasks = 0
            for phase in path_data.get("phases", []):
                total_tasks += len(phase.get("tasks", []))

            # 将当前 day 的所有任务标记为完成（全部三个子任务）
            for phase in path_data.get("phases", []):
                for task in phase.get("tasks", []):
                    if task.get("day") == current_day:
                        task_key = f"{task['day']}-{task['topic']}"
                        if task_key not in completed_tasks:
                            completed_tasks[task_key] = {"learn": False, "quiz": False, "code": False}
                        completed_tasks[task_key] = {"learn": True, "quiz": True, "code": True}

            progress["completed_tasks"] = completed_tasks
            fully_completed = sum(1 for k in completed_tasks if _is_task_fully_complete(completed_tasks[k]))
            progress["overall_progress"] = round(fully_completed / total_tasks * 100) if total_tasks > 0 else 0

            conn.execute(
                "UPDATE learning_paths SET progress_json = ?, updated_at = ? WHERE id = ?",
                (json.dumps(progress, ensure_ascii=False), datetime.now().isoformat(), path_row["id"])
            )
            conn.commit()

    conn.close()

    if completed:
        advanced = await _advance_learning_day(user_id)
        if advanced:
            # 天数推进了才删除旧任务，下次获取重新生成
            conn = get_db()
            conn.execute("DELETE FROM daily_tasks WHERE user_id = ? AND date = ?", (user_id, date))
            conn.commit()
            conn.close()

    return {"message": "任务状态已更新"}


async def _advance_learning_day(user_id: int) -> bool:
    """完成今日任务后推进学习路径的 current_day，返回是否实际推进"""
    conn = get_db()
    row = conn.execute(
        "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()

    if not row:
        conn.close()
        return False

    progress = json_load(row["progress_json"]) if row["progress_json"] else {}
    progress = _normalize_progress(progress)
    current_day = progress.get("current_day", 1)

    path_data = json_load(row["path_data_json"]) if row["path_data_json"] else {}
    completed_tasks = progress.get("completed_tasks", {})
    day_tasks = []
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("day") == current_day:
                day_tasks.append(_get_task_key(task["day"], task["topic"]))

    # 使用 _is_task_fully_complete 检查所有子任务是否完成（而非仅检查key存在）
    all_done = all(_is_task_fully_complete(completed_tasks.get(t, {})) for t in day_tasks) if day_tasks else True

    if all_done:
        progress["current_day"] = current_day + 1
        conn.execute(
            "UPDATE learning_paths SET progress_json = ?, updated_at = ? WHERE id = ?",
            (json.dumps(progress, ensure_ascii=False), datetime.now().isoformat(), row["id"])
        )
        conn.commit()
        conn.close()
        return True

    conn.commit()
    conn.close()
    return False

async def get_error_book(user_id: int, page: int = 1, page_size: int = 20) -> dict:
    """获取错题本"""
    conn = get_db()
    total = conn.execute(
        "SELECT COUNT(*) FROM error_questions WHERE user_id = ?", (user_id,)
    ).fetchone()[0]

    offset = (page - 1) * page_size
    rows = conn.execute(
        "SELECT * FROM error_questions WHERE user_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
        (user_id, page_size, offset)
    ).fetchall()
    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        qd = d.get("question_data", "{}")
        if isinstance(qd, str):
            try:
                d["question_data"] = json_load(qd)
            except (json.JSONDecodeError, TypeError):
                d["question_data"] = {"question": qd[:200], "analysis": ""}
        elif isinstance(qd, dict):
            d["question_data"] = qd
        else:
            d["question_data"] = {}
        items.append(d)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size
    }

async def get_error_sessions(user_id: int) -> list:
    """获取错题按测评会话分组"""
    conn = get_db()
    # 有 session_id 的按 session 分组
    rows = conn.execute("""
        SELECT e.session_id, COUNT(*) as error_count,
               SUM(CASE WHEN e.reviewed = 1 THEN 1 ELSE 0 END) as reviewed_count,
               qs.stage, qs.score, qs.total,
               COALESCE(qs.completed_at, qs.created_at) as quiz_time
        FROM error_questions e
        LEFT JOIN quiz_sessions qs ON e.session_id = qs.id
        WHERE e.user_id = ?
        GROUP BY e.session_id, qs.stage, qs.score, qs.total, qs.completed_at, qs.created_at
        ORDER BY quiz_time DESC
    """, (user_id,)).fetchall()

    sessions = []
    for r in rows:
        stage = r["stage"] or "未知"
        score = r["score"] or 0
        total = r["total"] or 0
        quiz_time = r["quiz_time"] or ""
        # 统一处理 datetime 对象（PG）和字符串（SQLite）两种格式
        if quiz_time:
            if isinstance(quiz_time, datetime):
                display_time = quiz_time.strftime("%Y-%m-%d %H:%M")
            else:
                # '2026-06-06 09:53:39' 或 '2026-06-06T17:54:31.951562'
                display_time = quiz_time.replace("T", " ")[:16]
        else:
            display_time = ""
        sessions.append({
            "session_id": r["session_id"],
            "label": f"{stage}测评 ({score}/{total}分)" if quiz_time else "历史错题",
            "error_count": r["error_count"],
            "reviewed_count": r["reviewed_count"] or 0,
            "quiz_time": display_time,
            "stage": stage,
            "score": score,
            "total": total,
        })

    conn.close()
    return sessions


async def get_errors_by_session(user_id: int, session_id: int = None, page: int = 1, page_size: int = 50) -> dict:
    """获取指定会话的错题"""
    conn = get_db()
    if session_id is not None:
        total = conn.execute(
            "SELECT COUNT(*) FROM error_questions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id)
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM error_questions WHERE user_id = ? AND session_id = ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, session_id, page_size, offset)
        ).fetchall()
    else:
        total = conn.execute(
            "SELECT COUNT(*) FROM error_questions WHERE user_id = ? AND session_id IS NULL",
            (user_id,)
        ).fetchone()[0]
        offset = (page - 1) * page_size
        rows = conn.execute(
            "SELECT * FROM error_questions WHERE user_id = ? AND session_id IS NULL ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (user_id, page_size, offset)
        ).fetchall()

    conn.close()

    items = []
    for r in rows:
        d = dict(r)
        qd = d.get("question_data", "{}")
        if isinstance(qd, str):
            try:
                d["question_data"] = json_load(qd)
            except (json.JSONDecodeError, TypeError):
                d["question_data"] = {"question": qd[:200], "analysis": ""}
        elif isinstance(qd, dict):
            d["question_data"] = qd
        else:
            d["question_data"] = {}
        items.append(d)

    return {
        "items": items,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": max(1, (total + page_size - 1) // page_size)
    }


async def delete_errors_by_session(user_id: int, session_id: int = None) -> dict:
    """删除指定会话的所有错题"""
    conn = get_db()
    if session_id is not None:
        count = conn.execute(
            "SELECT COUNT(*) FROM error_questions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id)
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM error_questions WHERE user_id = ? AND session_id = ?",
            (user_id, session_id)
        )
    else:
        count = conn.execute(
            "SELECT COUNT(*) FROM error_questions WHERE user_id = ? AND session_id IS NULL",
            (user_id,)
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM error_questions WHERE user_id = ? AND session_id IS NULL",
            (user_id,)
        )
    conn.commit()
    conn.close()
    return {"deleted": count}


async def batch_delete_errors(user_id: int, error_ids: list[int]) -> dict:
    """批量删除错题（保留兼容）"""
    conn = get_db()
    deleted = 0
    for eid in error_ids:
        row = conn.execute(
            "SELECT id FROM error_questions WHERE id = ? AND user_id = ?",
            (eid, user_id)
        ).fetchone()
        if row:
            conn.execute("DELETE FROM error_questions WHERE id = ?", (eid,))
            deleted += 1
    conn.commit()
    conn.close()
    return {"deleted": deleted, "total": len(error_ids)}

def map_task_knowledge_to_categories(knowledge_text: str) -> list:
    """将任务知识点文本映射到题库分类（长关键词优先匹配，精准聚焦）"""
    from services.question_bank_service import KNOWLEDGE_CATEGORY_MAP
    from collections import Counter

    if not knowledge_text:
        return ["智能体基础概念"]

    # 按关键词长度降序匹配（"多智能体应用" > "智能体"），累加权重
    sorted_keywords = sorted(KNOWLEDGE_CATEGORY_MAP.keys(), key=len, reverse=True)
    category_scores = Counter()
    for keyword in sorted_keywords:
        if keyword in knowledge_text:
            category_scores[KNOWLEDGE_CATEGORY_MAP[keyword]] += len(keyword)

    if category_scores:
        # 只返回得分最高的 1-2 个分类，保证精准
        top = category_scores.most_common(2)
        return [cat for cat, _ in top]

    # 完全无匹配时，返回最通用的分类（而非全部6个）
    return ["智能体基础概念"]


async def generate_task_quiz(user_id: int, task_day: int, count: int = 10) -> dict:
    """为学习路径中指定天数的任务生成专项练习题"""
    # 1. 获取用户的学习路径
    path = await get_learning_path(user_id)
    if not path or not path.get("path_data"):
        return {"error": "没有找到学习路径，请先生成学习路径"}

    path_data = path["path_data"]

    # 2. 查找指定天数的任务（跳过复习任务）
    target_task = None
    for phase in path_data.get("phases", []):
        for task in phase.get("tasks", []):
            if task.get("day") == task_day and not task.get("remedial"):
                target_task = task
                break
        if target_task:
            break

    if not target_task:
        return {"error": f"未找到第{task_day}天的任务"}

    # 3. 任务知识点 → 题库分类 + 所属模块
    import os as _os
    knowledge_text = target_task.get("knowledge", "")

    # 先通过 knowledge_tags.json 精确查找知识点所属的分类
    from config import KNOWLEDGE_TAGS_PATH as _KT_PATH
    CATEGORY_TO_MODULE = {
        "智能体基础概念": "智能体基础通识",
        "大模型基座原理": "大模型与提示词工程",
        "提示词工程": "大模型与提示词工程",
        "智能体框架开发": "智能体四大核心能力模块",
        "智能体算法逻辑": "智能体四大核心能力模块",
        "多智能体应用": "多智能体系统",
    }

    exact_category = None
    if _os.path.exists(_KT_PATH):
        with open(_KT_PATH, 'r', encoding='utf-8') as f:
            kt_data = json.load(f)
        for cat_data in kt_data:
            for tag in cat_data.get("tags", []):
                if tag["name"] == knowledge_text:
                    exact_category = cat_data["category"]
                    break
            if exact_category:
                break

    # 精确匹配到分类就用精确分类，否则回退到关键词匹配
    if exact_category:
        focus_categories = [exact_category]
        task_module = CATEGORY_TO_MODULE.get(exact_category)
    else:
        focus_categories = map_task_knowledge_to_categories(knowledge_text)
        task_module = None
        for cat in focus_categories:
            mod = CATEGORY_TO_MODULE.get(cat)
            if mod:
                task_module = mod
                break

    # focus_knowledge: 模块名（触发模块级过滤）+ 分类名（触发知识点级过滤）
    combined_focus = []
    if task_module:
        combined_focus.append(task_module)
    combined_focus.extend(focus_categories)

    # 4. 根据学习深度确定出题难度阶段
    depth = path_data.get("learning_depth", "标准")
    depth_stage_map = {"基础": "入门", "标准": "进阶", "深入": "高阶"}
    stage = depth_stage_map.get(depth, "进阶")

    # 5. 加载已出过的题目（跨任务去重）
    used_questions = set()
    conn0 = get_db()
    row0 = conn0.execute(
        "SELECT progress_json FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
        (user_id,)
    ).fetchone()
    if row0 and row0["progress_json"]:
        try:
            prog = json_load(row0["progress_json"])
            used_questions = set(prog.get("used_question_texts", []))
        except:
            pass
    conn0.close()

    # 6. 调用诊断服务生成题目（传入knowledge_filter + exclude_ids）
    from services.diagnosis_service import generate_quiz
    result = await generate_quiz(
        user_id=user_id,
        stage=stage,
        count=count,
        focus_knowledge=combined_focus,
        knowledge_filter=knowledge_text,
        exclude_ids=used_questions,
        use_timer=False,
        timer_minutes=0
    )

    # 7. 将新出的题目加入已用集合
    new_texts = [q.get("question", "") for q in result.get("questions", [])]
    used_questions.update(new_texts)
    # 限制集合大小（保留最近500道）
    if len(used_questions) > 500:
        used_questions = set(list(used_questions)[-500:])

    # 8. 保存 task_quiz_map + used_question_texts, 用于后续自动记录
    #    直接存 task_key（"{day}-{topic}"），避免 submit 时再到 path_data 里查找匹配
    session_id = result.get("session_id")
    if session_id:
        task_key = _get_task_key(task_day, target_task.get("topic", ""))
        conn = get_db()
        row = conn.execute(
            "SELECT * FROM learning_paths WHERE user_id = ? AND status = 'active' ORDER BY updated_at DESC LIMIT 1",
            (user_id,)
        ).fetchone()
        if row:
            progress = json_load(row["progress_json"]) if row["progress_json"] else {}
            progress = _normalize_progress(progress)
            if "task_quiz_map" not in progress:
                progress["task_quiz_map"] = {}
            progress["task_quiz_map"][str(session_id)] = task_key
            progress["used_question_texts"] = list(used_questions)
            print(f"[generate_task_quiz] Saving task_quiz_map[{session_id}] = {task_key}")
            conn.execute(
                "UPDATE learning_paths SET progress_json = ? WHERE id = ?",
                (json.dumps(progress, ensure_ascii=False), row["id"])
            )
            conn.commit()
        conn.close()

    # 7. 附带任务上下文返回
    result["task_context"] = {
        "day": task_day,
        "topic": target_task.get("topic", ""),
        "knowledge": knowledge_text
    }

    return result



async def review_error(user_id: int, error_id: int) -> dict:
    """标记错题已复习"""
    conn = get_db()
    conn.execute(
        "UPDATE error_questions SET reviewed = 1 WHERE id = ? AND user_id = ?",
        (error_id, user_id)
    )
    conn.commit()
    conn.close()

    # 更新学习记录
    conn = get_db()
    error = conn.execute("SELECT * FROM error_questions WHERE id = ?", (error_id,)).fetchone()
    if error:
        conn.execute(
            "INSERT INTO learning_records (user_id, knowledge_tag, action_type, result_json) VALUES (?, ?, 'review_error', ?)",
            (user_id, error["knowledge_tag"], json.dumps({"error_id": error_id}, ensure_ascii=False))
        )
    conn.commit()
    conn.close()

    return {"message": "已标记为已复习"}


async def review_session_errors(user_id: int, session_id: int) -> dict:
    """将该会话下所有未复习的错题批量标记为已复习"""
    conn = get_db()
    cur = conn.execute(
        "UPDATE error_questions SET reviewed = 1 WHERE user_id = ? AND session_id = ? AND reviewed = 0",
        (user_id, session_id)
    )
    updated = cur.rowcount
    conn.commit()
    conn.close()

    # 为每道题记录学习活动
    if updated > 0:
        conn = get_db()
        errors = conn.execute(
            "SELECT id, knowledge_tag FROM error_questions WHERE session_id = ? AND user_id = ?",
            (session_id, user_id)
        ).fetchall()
        for e in errors:
            conn.execute(
                "INSERT INTO learning_records (user_id, knowledge_tag, action_type, result_json) VALUES (?, ?, 'review_error', ?)",
                (user_id, e["knowledge_tag"], json.dumps({"error_id": e["id"], "batch": True}, ensure_ascii=False))
            )
        conn.commit()
        conn.close()

    return {"reviewed_count": updated, "session_id": session_id}


async def generate_review_quiz(user_id: int, session_id: int = None, count: int = 10) -> dict:
    """错题重测：把错题本中的错题组装成一份可提交的重测卷，闭环回写

    - session_id 为空时取全部错题；否则只取指定测评会话的错题
    - 优先选未复习(reviewed=0)的错题，不足时用已复习的补齐
    - 每题保留 source_error_id，提交重测卷后由 submit_quiz 回写"已攻克"
    """
    import uuid as _uuid
    conn = get_db()
    if session_id is not None:
        rows = conn.execute(
            "SELECT * FROM error_questions WHERE user_id = ? AND session_id = ? "
            "ORDER BY reviewed ASC, created_at DESC",
            (user_id, session_id)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM error_questions WHERE user_id = ? "
            "ORDER BY reviewed ASC, created_at DESC",
            (user_id,)
        ).fetchall()
    conn.close()

    if not rows:
        return {"error": "错题本暂无错题，无法生成重测卷"}

    # 组装阶段按画像调整（#34）：未复习优先（SQL 已排序），其中主口径薄弱标签的错题再优先
    try:
        from services.personalization_service import get_weak_tags
        weak_set = set(get_weak_tags(user_id, limit=6))
    except Exception:
        weak_set = set()
    if weak_set:
        rows = sorted(rows, key=lambda r: (r["reviewed"], 0 if r["knowledge_tag"] in weak_set else 1))

    questions = []
    for r in rows[:count]:
        d = dict(r)
        qd = d.get("question_data", "{}")
        if isinstance(qd, str):
            try:
                qd = json_load(qd)
            except (json.JSONDecodeError, TypeError):
                qd = {}
        if not isinstance(qd, dict):
            qd = {}
        if not qd.get("question"):
            continue
        questions.append({
            "question_id": f"rq_{_uuid.uuid4().hex[:8]}",
            "question": qd.get("question", ""),
            "options": qd.get("options", []),
            "question_type": qd.get("question_type", ""),
            "answer": qd.get("correct_answer", d.get("correct_answer", "")),
            "analysis": qd.get("analysis", ""),
            "option_analysis": qd.get("option_analysis", {}),
            "knowledge_tag": qd.get("knowledge_tag", d.get("knowledge_tag", "")),
            "knowledge_point": qd.get("knowledge_point", ""),
            "difficulty": qd.get("difficulty", ""),
            "code": qd.get("code", ""),
            "source_error_id": d.get("id"),
        })

    if not questions:
        return {"error": "错题数据不完整，无法生成重测卷"}

    # 保存重测会话（stage 标记为"错题重测"，供提交时识别并回写）
    conn = get_db()
    cursor = conn.execute(
        "INSERT INTO quiz_sessions (user_id, stage, questions_json, status) VALUES (?, ?, ?, 'pending')",
        (user_id, "错题重测", json.dumps(questions, ensure_ascii=False))
    )
    sid = cursor.lastrowid
    conn.execute(
        "INSERT INTO learning_records (user_id, knowledge_tag, action_type, result_json) VALUES (?, ?, 'review_quiz_start', ?)",
        (user_id, "错题重测", json.dumps(
            {"session_id": sid, "count": len(questions), "source_session_id": session_id},
            ensure_ascii=False
        ))
    )
    conn.commit()
    conn.close()

    return {
        "session_id": sid,
        "questions": questions,
        "total": len(questions),
        "stage": "错题重测",
        "task_context": {
            "topic": "错题重测",
            "knowledge": "错题巩固",
            "day": None,
        },
        "use_timer": False,
        "timer_minutes": 0,
    }
