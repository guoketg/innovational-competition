"""伴随式学习服务"""
import json
from datetime import datetime
from services.ai_service import call_llm, extract_json_object, LEARNING_PATH_PROMPT
from services.diagnosis_service import get_user_knowledge_profile, get_all_tags_flat, generate_quiz
from services.question_bank_service import KNOWLEDGE_CATEGORY_MAP
from database import get_db, json_load

async def generate_learning_path(user_id: int, goal: str = "", timeline: str = "", learning_depth: str = "标准", diagnostic_session_id: int = None, modules: list = None,
                                 target_tags: list = None, weekly_hours: float = None,
                                 deadline_weeks: int = None, preferred_mode: str = "") -> dict:
    """生成个性化学习路径
    Args:
        diagnostic_session_id: 可选，诊断测试的 session ID。
        modules: 可选，用户选中的模块名列表（如 ["线性结构", "排序算法"]）。
                 当提供时，从对应模块知识中直接构建路径，不调用LLM。
        target_tags: 可选，目标知识点 tag 列表，会优先排进路线并保证覆盖。
        weekly_hours / deadline_weeks: 可选，时间预算，用于把路线压缩到可完成的范围。
        preferred_mode: 可选，编排偏好：均衡 / 补弱优先 / 目标优先 / 省时优先。
    """
    learner_preferences = {
        "target_tags": target_tags or [],
        "weekly_hours": weekly_hours,
        "deadline_weeks": deadline_weeks,
        "preferred_mode": preferred_mode or "",
    }
    # ===== 模块选择模式：直接从知识结构构建学习路径 =====
    if modules and len(modules) > 0:
        from services.agent_course import TRACK_NAMES, plan_course_path

        # 新版项目制课程使用固定依赖顺序与显式实验绑定，不再从知识标签中随机拼装。
        # 生成前先判定学生水平，再按 skip / reorder / depth 三件事做个性化编排。
        if any(module in TRACK_NAMES for module in modules):
            selected = [name for name in TRACK_NAMES if name in modules]
            if not selected:
                raise ValueError("请选择至少一个 Agent 实战阶段")
            level_profile = _build_level_profile(user_id, diagnostic_session_id, learner_preferences)
            graph_context = _build_graph_context(user_id, level_profile.get("mastery"))
            return await _save_learning_path(
                user_id,
                plan_course_path(
                    selected,
                    level_profile,
                    learning_depth,
                    prereq_map=graph_context["prereq_map"],
                    graph_context=graph_context,
                ),
            )

        import os as _os
        # 模块名 → 分类名映射
        MODULE_CATEGORY_MAP = {
            "线性结构": "线性结构",
            "树与堆": "树与堆",
            "图与并查集": "图与并查集",
            "排序算法": "排序算法",
            "哈希与缓存": "哈希与缓存",
            "算法工具箱与综合": "算法工具箱与综合",
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
        goal=goal or (user["learning_goal"] if user and user["learning_goal"] else "系统掌握数据结构与算法知识"),
        timeline=timeline or "2周",
        learning_depth=learning_depth,
        knowledge_system=knowledge_system_str,
        prerequisite_chain=prereq_escaped
    )

    # 学习路径生成使用更长超时（180s）和更大 max_tokens（容纳长JSON）
    # 个性化出口（#34）：LLM 调用注入完整画像（与 QA #22 / 教程 #26 同一主口径），异常回退基础提示
    base_system = "你是数据结构与算法课程的学习规划师，只输出JSON。"
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
        "2周学会哈希表" → ["哈希与缓存"]
        "掌握图的最短路径" → ["图与并查集"]
        "学习排序算法" → ["排序算法"]
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


def _base_level_profile(user_id: int, diagnostic_session_id: int = None) -> dict:
    """判定学生起点，优先级：诊断结果 > 历史掌握度证据 > 注册信息。"""
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


def _build_error_profile(mastery_detail: dict, names: dict) -> dict:
    """把答错记录整理成「错误画像」：错得多的知识点 + 对应常见误区。"""
    from services.agent_course import KNOWLEDGE_META

    items = []
    total_attempts = 0
    total_correct = 0
    for tag, detail in (mastery_detail or {}).items():
        attempts = int((detail or {}).get("quiz_attempts") or 0)
        if attempts <= 0:
            continue
        correct = int((detail or {}).get("quiz_correct") or 0)
        total_attempts += attempts
        total_correct += correct
        wrong = max(0, attempts - correct)
        if wrong <= 0:
            continue
        meta = KNOWLEDGE_META.get(tag) or {}
        items.append({
            "tag": tag,
            "name": names.get(tag) or tag,
            "attempts": attempts,
            "correct": correct,
            "wrong": wrong,
            "accuracy": round(correct / attempts, 3),
            "misconceptions": list(meta.get("misconceptions") or [])[:2],
        })
    items.sort(key=lambda item: (-item["wrong"], item["accuracy"], -item["attempts"]))
    accuracy = round(total_correct / total_attempts, 3) if total_attempts else None
    if not items:
        note = "还没有答错记录；做过几次小测后，这里会列出最需要纠正的知识点。"
    else:
        names_text = "、".join(item["name"] for item in items[:3])
        note = f"错得最多的是「{names_text}」，路线会把这些知识点往前排，并附上常见误区提示。"
    return {
        "total_attempts": total_attempts,
        "correct_attempts": total_correct,
        "wrong_attempts": total_attempts - total_correct,
        "accuracy": accuracy,
        "top_error_tags": items[:6],
        "note": note,
    }


def _build_mastery_uncertainty(mastery_detail: dict, names: dict) -> dict:
    """掌握度不确定度：练习证据越少越不确定，路线会先安排一次小测确认。"""
    by_tag = {}
    for tag, name in names.items():
        detail = (mastery_detail or {}).get(tag) or {}
        evidence = int(detail.get("evidence_count") or 0)
        confidence = float(detail.get("confidence") or 0)
        uncertainty = round(max(0.0, 1.0 - confidence), 3)
        by_tag[tag] = {
            "name": name,
            "evidence_count": evidence,
            "confidence": round(confidence, 3),
            "uncertainty": uncertainty,
            "needs_check": uncertainty >= 0.6,
        }
    values = [item["uncertainty"] for item in by_tag.values()]
    top = sorted(
        ({"tag": tag, **item} for tag, item in by_tag.items() if item["needs_check"]),
        key=lambda item: -item["uncertainty"],
    )[:8]
    return {
        "average": round(sum(values) / len(values), 3) if values else 0.0,
        "top_uncertain_tags": top,
        "by_tag": by_tag,
        "note": (
            "还没有足够的练习证据，掌握度先按中性值估计；先做几道小测会让路线更准。"
            if top else "大部分知识点的掌握度已经有练习证据支撑。"
        ),
    }


def _build_level_profile(user_id: int, diagnostic_session_id: int = None,
                         preferences: dict = None) -> dict:
    """在水平判定之上补齐学习者模型：目标、时间预算、偏好、错误画像、不确定度。"""
    from services.agent_course import course_point_names

    preferences = preferences or {}
    profile = _base_level_profile(user_id, diagnostic_session_id)
    names = course_point_names()
    valid_tags = set(names)

    try:
        historical = _mastery_by_knowledge(user_id)
    except Exception:
        historical = {}
    mastery = {
        tag: round(float(score), 3)
        for tag, score in historical.items()
        if tag in valid_tags and isinstance(score, (int, float))
    }
    if diagnostic_session_id:
        try:
            diagnostic_scores = _diagnostic_tag_scores(user_id, diagnostic_session_id)
        except Exception:
            diagnostic_scores = {}
        mastery.update({
            tag: round(float(score), 3)
            for tag, score in diagnostic_scores.items()
            if tag in valid_tags and isinstance(score, (int, float))
        })

    try:
        mastery_detail = _mastery_detail_by_knowledge(user_id)
    except Exception:
        mastery_detail = {}

    profile["mastery"] = mastery
    profile["weak_tags"] = [tag for tag, score in mastery.items() if score < 0.4]
    profile["mastered_tags"] = [tag for tag, score in mastery.items() if score >= 0.7]

    requested_targets = preferences.get("target_tags") or []
    target_tags = [tag for tag in dict.fromkeys(requested_targets) if tag in valid_tags]
    mode = str(preferences.get("preferred_mode") or "").strip()
    if mode not in ("均衡", "补弱优先", "目标优先", "省时优先"):
        mode = ""

    weekly_hours = preferences.get("weekly_hours")
    deadline_weeks = preferences.get("deadline_weeks")
    weekly_minutes = round(float(weekly_hours) * 60) if isinstance(weekly_hours, (int, float)) else None
    budget_minutes = (
        weekly_minutes * int(deadline_weeks)
        if weekly_minutes and isinstance(deadline_weeks, int) and deadline_weeks > 0
        else None
    )

    profile.update({
        "target_tags": target_tags,
        "target_names": [names.get(tag) for tag in target_tags],
        "time_budget": {
            "weekly_hours": weekly_hours,
            "weekly_minutes": weekly_minutes,
            "deadline_weeks": deadline_weeks,
            "budget_days": int(deadline_weeks) * 7 if isinstance(deadline_weeks, int) else None,
            "budget_minutes": budget_minutes,
            "source": "user" if budget_minutes else "none",
        },
        "preferences": {
            "mode": mode,
            "mode_label": mode or "自动选择",
            "target_count": len(target_tags),
            "explicit": bool(mode),
        },
        "error_profile": _build_error_profile(mastery_detail, names),
        "mastery_uncertainty": _build_mastery_uncertainty(mastery_detail, names),
    })
    return profile


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


QUICK_QUIZ_SIZE = 5


def _load_quick_quiz_questions() -> list:
    """读取快速测评题库；题库缺失时返回空列表。"""
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


def _quiz_tag_order() -> list:
    """按课程模块轮转排出知识点顺序，让抽题尽量覆盖不同模块。"""
    try:
        from services.agent_course import course_knowledge_points

        modules = {}
        for point in course_knowledge_points():
            modules.setdefault(point.get("module") or "其他", []).append(point["tag"])
    except Exception:
        return []

    order = []
    round_index = 0
    while True:
        added = False
        for tags in modules.values():
            if round_index < len(tags):
                order.append(tags[round_index])
                added = True
        if not added:
            break
        round_index += 1
    return order


def _answered_quick_quiz_tags(user_id: int) -> set:
    """已经产生过答题证据的知识点，用于优先抽尚未诊断的节点。"""
    try:
        from services.knowledge_tracking import quiz_evidence

        return {
            tag for tag, item in quiz_evidence(user_id).items()
            if item.get("attempts")
        }
    except Exception:
        return set()


def _select_quick_quiz_questions(user_id: int, count: int = QUICK_QUIZ_SIZE,
                                 knowledge_tag: str = "") -> list:
    """抽题：指定知识点时单点出题，否则优先抽尚未诊断的节点并跨模块轮转。"""
    questions = _load_quick_quiz_questions()
    if not questions:
        return []

    by_tag = {}
    for question in questions:
        tag = question.get("knowledge_tag")
        if tag and tag not in by_tag:
            by_tag[tag] = question

    if knowledge_tag:
        question = by_tag.get(knowledge_tag)
        return [question] if question else []

    answered = _answered_quick_quiz_tags(user_id)
    order = [tag for tag in _quiz_tag_order() if tag in by_tag]
    order += [tag for tag in by_tag if tag not in order]
    prioritized = [tag for tag in order if tag not in answered] + \
                  [tag for tag in order if tag in answered]
    return [by_tag[tag] for tag in prioritized[:max(1, count)]]


def start_quick_quiz(user_id: int, knowledge_tag: str = "",
                     count: int = QUICK_QUIZ_SIZE) -> dict:
    """开始快速测评：默认抽 5 道并优先未诊断节点；传 knowledge_tag 可单点补测。"""
    knowledge_tag = (knowledge_tag or "").strip()
    questions = _select_quick_quiz_questions(user_id, count, knowledge_tag)
    if not questions and knowledge_tag:
        raise ValueError("该知识点暂未配置测评题")
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
            graph_context = _build_graph_context(user_id)
            similar_map = graph_context.get("similar") or {}
            name_map = graph_context.get("names") or {}
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
                knowledge_name = name_map.get(item["knowledge_tag"]) or item["knowledge_tag"]
                review_task.update({
                    "topic": f"个性化复习：{knowledge_name}",
                    "knowledge": source.get("knowledge") or item["knowledge_tag"],
                    "action": f"系统检测到你对「{knowledge_name}」的熟悉程度较低，建议返回编程实验重点复习。",
                    "check": "重新通过基本测试、用自己的话解释关键实现，并完成变式迁移",
                    "personalized_review": True,
                    "mastery_score": item["mastery_score"],
                    "basic_score": item["basic_score"],
                    "explanation_score": item["explanation_score"],
                    "transfer_score": item["transfer_score"],
                    "source_topic": source.get("topic"),
                })
                # 相似知识点 → 复习时顺手做一次「对比学习」
                similar = similar_map.get(item["knowledge_tag"]) or []
                if similar:
                    first = similar[0]
                    review_task["similar_topics"] = similar[:3]
                    review_task["compare_hint"] = (
                        f"复习时可以和「{first.get('name')}」对比："
                        f"{first.get('reason') or '概念相近，容易混淆'}"
                    )
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
    """掌握度主口径：课程知识点 -> 0~1 分数。

    由知识追踪服务合并「平时小测 + 代码实验」两类证据，证据少时平滑到 50%，
    避免只做对一题就被判定为已掌握。
    """
    from services import knowledge_tracking

    return knowledge_tracking.mastery_by_knowledge(user_id)


def _mastery_detail_by_knowledge(user_id: int) -> dict:
    """掌握度明细：tag -> {score, last_activity_at, confidence, evidence_count, ...}。

    last_activity_at 供图谱判断掌握度是否过期；confidence / evidence_count 供界面
    说明这个分数有多可信、由几次练习得出。
    """
    from services import knowledge_tracking

    return knowledge_tracking.mastery_detail_by_knowledge(user_id)


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


def _build_graph_context(user_id: int, mastery: dict = None, mastery_meta: dict = None) -> dict:
    """读取用户知识图谱，组装路径编排真正使用的图谱上下文。

    - prereq_map：专家先修表 + AI 图谱补充的先修边（仅采纳已审核通过的高置信边）；
    - readiness：沿先修边传播出的就绪度（前置薄弱会卡住后继，未诊断前置单独标记）；
    - similar：相似知识点，供对比学习提示；
    - names：tag → 展示名，用于把内部标签翻译成用户能看懂的名字。

    没有图谱时退回专家先修表，行为与升级前一致。
    """
    from services import knowledge_graph_service as kg

    expert = _load_prerequisites()
    graph = None
    try:
        graph = kg.get_knowledge_graph(user_id)
    except Exception:
        graph = None

    if not graph:
        return {
            "has_graph": False,
            "graph": None,
            "source": "expert",
            "prereq_map": expert,
            "added_edges": [],
            "readiness": {},
            "similar": {},
            "names": {},
        }

    prereq_map, added_edges = kg.effective_prerequisite_map(graph, expert)
    if mastery is None:
        try:
            mastery = _mastery_by_knowledge(user_id)
        except Exception:
            mastery = {}
    if mastery_meta is None:
        try:
            mastery_meta = _mastery_detail_by_knowledge(user_id)
        except Exception:
            mastery_meta = {}

    try:
        from services.teaching_policy_service import MASTERY_HIGH, MASTERY_LOW
    except Exception:
        MASTERY_HIGH, MASTERY_LOW = 0.7, 0.4

    return {
        "has_graph": True,
        "graph": graph,
        "source": graph.get("generated_by") or "llm",
        "prereq_map": prereq_map,
        "added_edges": added_edges,
        "readiness": kg.propagate_readiness(
            graph, prereq_map, mastery, MASTERY_LOW, MASTERY_HIGH, mastery_meta=mastery_meta
        ),
        "similar": kg.similar_index(graph),
        "names": kg.node_name_index(graph),
    }


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
    from services.agent_course import TRACK_NAMES, course_point_names, plan_knowledge_path

    path = await get_learning_path(user_id)
    if not path:
        return {
            "has_path": False,
            "roadmap": None,
            "knowledge_path": None,
            "counterfactual": None,
            "learner_profile": None,
            "path_strategy": None,
            "path_alternatives": [],
            "path_history": [],
            "available_tracks": TRACK_NAMES,
            "graph": {
                "has_graph": False,
                "source": "expert",
                "merged_edges": 0,
                "merged_edges_detail": [],
                "blocked_stations": 0,
                "remedial_stations": 0,
                "gated_stations": 0,
                "updated_at": None,
                "path_operator": None,
            },
        }

    path_data = path.get("path_data") or {}
    progress = path.get("progress") or {}
    completed_tasks = progress.get("completed_tasks", {}) or {}
    current_day = progress.get("current_day", 1)

    mastery_detail = _mastery_detail_by_knowledge(user_id)
    mastery_map = {tag: item["score"] for tag, item in mastery_detail.items()}
    graph_context = _build_graph_context(user_id, mastery_map, mastery_detail)
    prereq_map = graph_context["prereq_map"]
    readiness_map = graph_context.get("readiness") or {}
    node_names = {**course_point_names(), **(graph_context.get("names") or {})}

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
            readiness = readiness_map.get(knowledge) or {}
            blockers = [node_names.get(b) or b for b in (readiness.get("root_blockers") or []) if b]
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
                "mastery_confidence": (mastery_detail.get(knowledge) or {}).get("confidence"),
                "mastery_confidence_label": (mastery_detail.get(knowledge) or {}).get("confidence_label"),
                "mastery_evidence": (mastery_detail.get(knowledge) or {}).get("evidence_count"),
                "sub_tasks": {k: bool(status_map.get(k, False)) for k in ("learn", "quiz", "code")},
                "completed_count": _count_completed_sub_tasks(status_map),
                "is_remedial": bool(
                    task.get("remedial") or task.get("remedial_prerequisite") or task.get("remedial_focus")
                ),
                "remedial_for": task.get("remedial_for") or [],
                "graph_reason": task.get("graph_reason") or "",
                "graph_readiness": readiness.get("state") if readiness else None,
                "graph_readiness_score": readiness.get("score") if readiness else None,
                "graph_own_mastery": readiness.get("own_mastery") if readiness else None,
                "graph_undiagnosed": bool(readiness.get("undiagnosed")) if readiness else False,
                "graph_parents": [
                    {**parent, "name": node_names.get(parent.get("tag")) or parent.get("tag")}
                    for parent in (readiness.get("parents") or [])
                ],
                "graph_blockers": blockers,
                "graph_gated": bool(task.get("graph_gated")),
                "skippable": bool(task.get("skippable")),
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
        elif any(p not in done_knowledge for p in station["prerequisites"]) \
                or station.get("graph_readiness") == "blocked":
            # 图谱判定「前置没打牢」的站点同样锁定，即使课程表里的直接先修已完成
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

    graph_operator = (path_data.get("applied_operators") or {}).get("graph") or {}
    current_graph = graph_context.get("graph") or {}
    path_needs_apply = bool(
        graph_context["has_graph"]
        and (
            not graph_operator.get("applied")
            or graph_operator.get("graph_updated_at") != current_graph.get("updated_at")
        )
    )

    # 知识点级路线：44 个知识点全部进入序列，项目只作为练习资源挂在这里。
    # 学习者模型（目标/预算/偏好/错误画像/不确定度）一并传入，参与排序与展示。
    level_profile = path_data.get("level_profile") or {}
    knowledge_path = plan_knowledge_path(
        mastery=mastery_map,
        prereq_map=prereq_map,
        graph_context=graph_context,
        selected_tracks=path_data.get("modules_selected") or None,
        level_profile=level_profile,
        mastery_detail=mastery_detail,
    )

    counterfactual = build_path_counterfactual(
        mastery=mastery_map,
        prereq_map=prereq_map,
        graph_context=graph_context,
        level_profile=level_profile,
        mastery_detail=mastery_detail,
        baseline_path=knowledge_path,
        selected_tracks=path_data.get("modules_selected") or None,
    )

    error_profile = level_profile.get("error_profile") or {}
    uncertainty = level_profile.get("mastery_uncertainty") or {}
    learner_profile = {
        "level": level_profile.get("level"),
        "level_label": level_profile.get("level_label"),
        "source": level_profile.get("source"),
        "correct_rate": level_profile.get("correct_rate"),
        "target_tags": level_profile.get("target_tags") or [],
        "target_names": level_profile.get("target_names") or [],
        "time_budget": level_profile.get("time_budget") or {},
        "preferences": level_profile.get("preferences") or {},
        "error_profile": {
            "wrong_attempts": error_profile.get("wrong_attempts"),
            "accuracy": error_profile.get("accuracy"),
            "top_error_tags": (error_profile.get("top_error_tags") or [])[:3],
            "note": error_profile.get("note") or "",
        },
        "mastery_uncertainty": {
            "average": uncertainty.get("average"),
            "top_uncertain_tags": (uncertainty.get("top_uncertain_tags") or [])[:5],
            "note": uncertainty.get("note") or "",
        },
    }


    return {
        "has_path": True,
        "curriculum_version": path_data.get("curriculum_version"),
        "learning_depth": path_data.get("learning_depth"),
        "updated_at": path.get("updated_at"),
        "knowledge_path": knowledge_path,
        "counterfactual": counterfactual,
        "learner_profile": learner_profile,
        "path_strategy": path_data.get("path_strategy") or knowledge_path.get("path_strategy"),
        "path_alternatives": path_data.get("alternatives") or [],
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
        "graph": {
            "has_graph": graph_context["has_graph"],
            "source": graph_context["source"],
            "merged_edges": len(graph_context.get("added_edges") or []),
            "merged_edges_detail": [
                {
                    "source": item.get("source"),
                    "source_name": node_names.get(item.get("source")) or item.get("source"),
                    "target": item.get("target"),
                    "target_name": node_names.get(item.get("target")) or item.get("target"),
                    "reason": item.get("reason") or "",
                    "confidence": item.get("confidence"),
                    "evidence": item.get("evidence") or "",
                }
                for item in (graph_context.get("added_edges") or [])[:5]
            ],
            "blocked_stations": sum(1 for s in stations if s.get("graph_readiness") == "blocked"),
            "remedial_stations": sum(1 for s in stations if s.get("is_remedial")),
            "gated_stations": sum(1 for s in stations if s.get("graph_gated")),
            "undiagnosed_stations": sum(1 for s in stations if s.get("graph_undiagnosed")),
            "updated_at": current_graph.get("updated_at"),
            "path_operator": graph_operator or None,
            "remedial_links": [
                {
                    **item,
                    "blocker_name": node_names.get(item.get("blocker"))
                                    or item.get("blocker_name") or item.get("blocker"),
                }
                for item in (graph_operator.get("remedial_links") or [])
            ],
            "discarded_edges": current_graph.get("discarded_edges") or [],
            "pending_edges": (current_graph.get("stats") or {}).get("pending_edges", 0),
            "rejected_edges": (current_graph.get("stats") or {}).get("rejected_edges", 0),
            "path_needs_apply": path_needs_apply,
            "needs_apply_reason": (
                "知识图谱更新后还没有重排路径，当前站序仍是上一次的编排结果。"
                if path_needs_apply else ""
            ),
        },
        "available_tracks": TRACK_NAMES,
        "review_notice": path_data.get("personalized_review"),
        "path_history": _load_path_versions(user_id, limit=5),
    }


# ── 路径级反事实解释（#49）─────────────────────────────────────────────

def _minutes_before_unit(units_by_tag: dict, target_tag: str) -> int:
    """按当前序列，学到目标知识点之前还要投入多少分钟（不含已完成）。"""
    target = units_by_tag.get(target_tag)
    if not target:
        return 0
    return sum(
        int(unit.get("estimated_minutes") or 0)
        for unit in units_by_tag.values()
        if int(unit.get("order") or 0) <= int(target.get("order") or 0)
        and unit.get("status") != "done"
    )


def build_path_counterfactual(mastery: dict, prereq_map: dict, graph_context: dict,
                              level_profile: dict, mastery_detail: dict,
                              baseline_path: dict, selected_tracks: list = None,
                              max_candidates: int = 4) -> dict:
    """回答「先补哪个知识点最划算」：把候选知识点假设为已掌握，重排一遍路径做对比。

    只做假设推演，不改任何数据：
    1. 找出当前被卡住（blocked）的知识点，取最近的一个作为目标；
    2. 候选 = 卡住它的根因知识点；
    3. 逐个假设「已掌握这个知识点（95%）」，重新传播就绪度 + 重排路径；
    4. 对比目标提前了几步、少花多少分钟、顺带解锁了多少个知识点。
    """
    from services.agent_course import plan_knowledge_path
    from services import knowledge_graph_service as kg

    units = (baseline_path or {}).get("units") or []
    if not units:
        return {"available": False, "reason": "还没有生成学习路径，暂时无法做对比推演", "options": []}

    units_by_tag = {unit["tag"]: unit for unit in units}
    locked_units = [unit for unit in units if unit.get("status") == "locked"]
    if not locked_units:
        return {
            "available": False,
            "reason": "当前没有被卡住的知识点，按现有路线继续学即可",
            "options": [],
        }

    target = min(locked_units, key=lambda unit: int(unit.get("order") or 0))
    target_tag = target["tag"]

    baseline_minutes = _minutes_before_unit(units_by_tag, target_tag)
    baseline_order = int(target.get("order") or 0)

    candidate_tags = []
    for unit in locked_units:
        for tag in unit.get("blocker_tags") or []:
            if tag in units_by_tag and tag not in candidate_tags:
                candidate_tags.append(tag)
    if not candidate_tags:
        candidate_tags = [
            item.get("tag") for item in (target.get("prerequisites") or [])
            if item.get("tag") in units_by_tag
        ]
    if not candidate_tags:
        return {
            "available": False,
            "reason": f"「{target.get('name') or target_tag}」被卡住，但没有记录到具体的前置知识点",
            "options": [],
        }

    try:
        from services.teaching_policy_service import MASTERY_HIGH, MASTERY_LOW
    except Exception:
        MASTERY_HIGH, MASTERY_LOW = 0.7, 0.4

    graph = graph_context.get("graph")
    has_readiness = bool(graph_context.get("readiness"))
    weekly_hours = (level_profile.get("time_budget") or {}).get("weekly_hours")
    try:
        weekly_hours = float(weekly_hours) if weekly_hours else None
    except (TypeError, ValueError):
        weekly_hours = None

    now = datetime.now()
    options = []
    for tag in candidate_tags[:12]:
        baseline_unit = units_by_tag[tag]
        if baseline_unit.get("status") == "done":
            continue

        mastered = dict(mastery or {})
        mastered[tag] = 0.95
        detail = dict(mastery_detail or {})
        tag_detail = dict(detail.get(tag) or {})
        tag_detail["score"] = 0.95
        tag_detail["last_activity_at"] = now.isoformat()
        detail[tag] = tag_detail

        context = dict(graph_context)
        if has_readiness:
            context["readiness"] = kg.propagate_readiness(
                graph, prereq_map, mastered, MASTERY_LOW, MASTERY_HIGH, mastery_meta=detail
            )
        simulated = plan_knowledge_path(
            mastery=mastered,
            prereq_map=prereq_map,
            graph_context=context,
            selected_tracks=selected_tracks,
            level_profile=level_profile,
            mastery_detail=detail,
        )
        sim_units = {unit["tag"]: unit for unit in simulated.get("units") or []}
        sim_target = sim_units.get(target_tag)
        if not sim_target:
            continue

        unlocked = [
            {"tag": unit["tag"], "name": unit.get("name") or unit["tag"]}
            for unit in sim_units.values()
            if units_by_tag.get(unit["tag"], {}).get("status") == "locked"
            and unit.get("status") != "locked"
        ]
        unlocked_minutes = sum(
            int((sim_units.get(item["tag"]) or {}).get("estimated_minutes") or 0)
            for item in unlocked
        )
        unlocked_weeks = (
            round(unlocked_minutes / 60 / weekly_hours, 1)
            if weekly_hours and unlocked_minutes > 0 else None
        )

        cost_minutes = int(baseline_unit.get("estimated_minutes") or 0)
        counted_in_sim = (
            int(sim_target.get("order") or 0) >= int(sim_units[tag].get("order") or 0)
            and sim_units[tag].get("status") != "done"
        )
        sim_minutes = _minutes_before_unit(sim_units, target_tag)
        if not counted_in_sim:
            sim_minutes += cost_minutes

        saved_minutes = baseline_minutes - sim_minutes
        steps_saved = baseline_order - int(sim_target.get("order") or 0)
        weeks_saved = (
            round(saved_minutes / 60 / weekly_hours, 1)
            if weekly_hours and saved_minutes > 0 else None
        )

        parts = [f"先补「{baseline_unit.get('name') or tag}」"]
        if unlocked:
            parts.append(f"能解锁 {len(unlocked)} 个知识点（少卡 {len(unlocked)} 步）")
            if unlocked_weeks:
                parts.append(f"这些内容约 {unlocked_weeks:g} 周学时")
            elif unlocked_minutes:
                parts.append(f"这些内容约 {unlocked_minutes} 分钟学时")
        if steps_saved > 0:
            parts.append(f"目标「{target.get('name') or target_tag}」提前 {steps_saved} 步")
        if saved_minutes > 0:
            text = f"少花约 {saved_minutes} 分钟"
            if weeks_saved:
                text += f"（按每周 {weekly_hours:g} 小时算，约提前 {weeks_saved:g} 周）"
            parts.append(text)
        if len(parts) == 1:
            parts.append("对当前路线没有明显帮助")

        options.append({
            "tag": tag,
            "name": baseline_unit.get("name") or tag,
            "module": baseline_unit.get("module") or "",
            "mastery": baseline_unit.get("mastery"),
            "mastery_band": baseline_unit.get("mastery_band"),
            "study_minutes": cost_minutes,
            "unlocked_count": len(unlocked),
            "unlocked": unlocked[:8],
            "unlocked_minutes": unlocked_minutes,
            "unlocked_weeks": unlocked_weeks,
            "steps_saved": max(steps_saved, 0),
            "minutes_saved": saved_minutes,
            "weeks_saved": weeks_saved,
            "reason": "，".join(parts),
            "_score": (len(unlocked), saved_minutes, steps_saved),
        })

    options.sort(key=lambda item: item["_score"], reverse=True)
    options = [{key: value for key, value in item.items() if key != "_score"}
               for item in options[:max_candidates]]

    return {
        "available": bool(options),
        "question": f"想更早学「{target.get('name') or target_tag}」，先补哪个最划算？",
        "target": {
            "tag": target_tag,
            "name": target.get("name") or target_tag,
            "order": baseline_order,
            "mastery": target.get("mastery"),
            "mastery_band": target.get("mastery_band"),
            "blockers": target.get("blockers") or [],
        },
        "baseline": {
            "locked_count": len(locked_units),
            "minutes_to_target": baseline_minutes,
            "target_order": baseline_order,
        },
        "weekly_hours": weekly_hours,
        "best": options[0] if options else None,
        "options": options,
        "assumption": "推演时假设候选知识点已达到 95% 掌握度，其他条件不变；不会改动你的真实学习记录。",
        "reason": "" if options else "暂时没有能明显缩短路线的补强项",
    }


# ── 路径版本与自动重排（#45）─────────────────────────────────────────────

_PATH_VERSIONS_TABLE_READY = False


def _ensure_path_versions_table() -> bool:
    """确保路径版本表存在。

    线上 PostgreSQL 的预建表由运维同步；这里再用 CREATE TABLE IF NOT EXISTS 兜底，
    保证新环境（或还没执行建表脚本的环境）也能正常记录版本。
    """
    global _PATH_VERSIONS_TABLE_READY
    if _PATH_VERSIONS_TABLE_READY:
        return True
    try:
        conn = get_db()
        conn.execute(
            """CREATE TABLE IF NOT EXISTS learning_path_versions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                path_id INTEGER,
                version INTEGER NOT NULL,
                trigger TEXT DEFAULT 'manual',
                trigger_label TEXT DEFAULT '',
                reason_json TEXT DEFAULT '{}',
                diff_json TEXT DEFAULT '{}',
                snapshot_json TEXT DEFAULT '[]',
                summary TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )"""
        )
        conn.commit()
        conn.close()
        _PATH_VERSIONS_TABLE_READY = True
        return True
    except Exception as exc:
        print(f"[path_versions] 建表失败，本次不记录版本: {exc}")
        return False


def _path_snapshot(path_data: dict, progress: dict) -> list:
    """把一条路径压成紧凑快照，用于版本对比。"""
    completed = (progress or {}).get("completed_tasks") or {}
    snapshot = []
    for phase in (path_data or {}).get("phases", []):
        if phase.get("personalized_review"):
            continue
        for task in phase.get("tasks", []) or []:
            key = _get_task_key(task.get("day", 0), task.get("topic") or "")
            status = completed.get(key) or {}
            snapshot.append({
                "day": task.get("day"),
                "topic": task.get("topic") or "",
                "knowledge": task.get("knowledge") or "",
                "lab_id": task.get("lab_id") or "",
                "duration": task.get("duration") or "",
                "skippable": bool(task.get("skippable")),
                "gated": bool(task.get("graph_gated")),
                "phase": phase.get("name") or "",
                "status": {k: bool(status.get(k)) for k in ("learn", "quiz", "code")},
            })
    return snapshot


def _snapshot_key(item: dict) -> str:
    return "|".join(str(item.get(k) or "") for k in ("knowledge", "lab_id", "topic"))


def _snapshot_brief(item: dict) -> dict:
    return {
        "day": item.get("day"),
        "topic": item.get("topic") or "",
        "knowledge": item.get("knowledge") or "",
    }


def _diff_path_snapshots(old_snapshot: list, new_snapshot: list) -> dict:
    """对比新旧路径：哪些任务新增/移除/换位/改时长/变可快进。"""
    old_map = {_snapshot_key(item): item for item in old_snapshot or []}
    new_map = {_snapshot_key(item): item for item in new_snapshot or []}

    added = [_snapshot_brief(new_map[k]) for k in new_map if k not in old_map]
    removed = [_snapshot_brief(old_map[k]) for k in old_map if k not in new_map]

    moved, duration_changed, skippable_added, skippable_removed, gated_added, gated_removed = [], [], [], [], [], []
    for key in new_map:
        old_item = old_map.get(key)
        if not old_item:
            continue
        new_item = new_map[key]
        if old_item.get("day") != new_item.get("day"):
            moved.append({**_snapshot_brief(new_item), "old_day": old_item.get("day")})
        if (old_item.get("duration") or "") != (new_item.get("duration") or ""):
            duration_changed.append({
                **_snapshot_brief(new_item),
                "old_duration": old_item.get("duration") or "",
                "new_duration": new_item.get("duration") or "",
            })
        if not old_item.get("skippable") and new_item.get("skippable"):
            skippable_added.append(_snapshot_brief(new_item))
        if old_item.get("skippable") and not new_item.get("skippable"):
            skippable_removed.append(_snapshot_brief(new_item))
        if not old_item.get("gated") and new_item.get("gated"):
            gated_added.append(_snapshot_brief(new_item))
        if old_item.get("gated") and not new_item.get("gated"):
            gated_removed.append(_snapshot_brief(new_item))

    return {
        "added": added,
        "removed": removed,
        "moved": moved,
        "duration_changed": duration_changed,
        "skippable_added": skippable_added,
        "skippable_removed": skippable_removed,
        "gated_added": gated_added,
        "gated_removed": gated_removed,
        "counts": {
            "added": len(added),
            "removed": len(removed),
            "moved": len(moved),
            "duration_changed": len(duration_changed),
            "skippable_added": len(skippable_added),
            "skippable_removed": len(skippable_removed),
            "gated_added": len(gated_added),
            "gated_removed": len(gated_removed),
        },
    }


def _mastery_changes(old_mastery: dict, detail: dict) -> list:
    """找出「值得重排」的掌握度变化。

    判定标准（任一满足）：
    - 分数变化 ≥ 0.1；
    - 跨越 40% / 70% 分档；
    - 旧路径没有这个知识点的记录，但现在已经有了练习证据。
    """
    changes = []
    for tag, item in (detail or {}).items():
        new_score = item.get("score")
        if new_score is None:
            continue
        old_score = (old_mastery or {}).get(tag)
        band_before = _mastery_band(old_score)
        band_after = _mastery_band(new_score)
        delta = None if old_score is None else round(float(new_score) - float(old_score), 3)
        has_new_evidence = old_score is None and int(item.get("evidence_count") or 0) > 0
        significant = (
            has_new_evidence
            or (delta is not None and abs(delta) >= 0.1)
            or (old_score is not None and band_before != band_after)
        )
        if not significant:
            continue
        changes.append({
            "knowledge": tag,
            "before": None if old_score is None else round(float(old_score), 3),
            "after": round(float(new_score), 3),
            "delta": delta,
            "band_before": band_before,
            "band_after": band_after,
            "evidence_count": int(item.get("evidence_count") or 0),
        })
    changes.sort(key=lambda item: abs(item.get("delta") or 0), reverse=True)
    return changes


def _describe_replan(trigger_label: str, changes: list, diff: dict) -> str:
    """把变更翻译成一句人话，作为版本摘要。"""
    parts = []
    if changes:
        up = sum(1 for item in changes if (item.get("delta") or 0) > 0)
        down = sum(1 for item in changes if (item.get("delta") or 0) < 0)
        fresh = sum(1 for item in changes if item.get("before") is None)
        if up:
            parts.append(f"{up} 个知识点掌握度上升")
        if down:
            parts.append(f"{down} 个知识点掌握度下降")
        if fresh:
            parts.append(f"{fresh} 个知识点有了新的练习证据")
    counts = (diff or {}).get("counts") or {}
    if counts.get("skippable_added"):
        parts.append(f"{counts['skippable_added']} 个任务变为可快进")
    if counts.get("skippable_removed"):
        parts.append(f"{counts['skippable_removed']} 个任务取消快进")
    if counts.get("moved"):
        parts.append(f"{counts['moved']} 个任务调整了先后")
    if counts.get("duration_changed"):
        parts.append(f"{counts['duration_changed']} 个任务时长调整")
    if counts.get("added"):
        parts.append(f"新增 {counts['added']} 个补先修任务")
    if counts.get("removed"):
        parts.append(f"移除 {counts['removed']} 个任务")
    if counts.get("gated_added"):
        parts.append(f"{counts['gated_added']} 个任务被前置锁定")
    detail = "，".join(parts) if parts else "任务顺序和掌握度分档没有明显变化"
    return f"{trigger_label}后自动调整路线：{detail}"


def _record_path_version(user_id: int, path_id: int, trigger: str, trigger_label: str,
                         reason: dict, diff: dict, snapshot: list, summary: str):
    """写入一条路径版本，返回版本号；表不可用时返回 None。"""
    if not _ensure_path_versions_table():
        return None
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT MAX(version) AS max_version FROM learning_path_versions WHERE user_id = ?",
            (user_id,),
        ).fetchone()
        version = int((row["max_version"] if row else 0) or 0) + 1
        conn.execute(
            """INSERT INTO learning_path_versions
               (user_id, path_id, version, trigger, trigger_label, reason_json, diff_json, snapshot_json, summary)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                user_id,
                path_id,
                version,
                trigger,
                trigger_label,
                json.dumps(reason or {}, ensure_ascii=False),
                json.dumps(diff or {}, ensure_ascii=False),
                json.dumps(snapshot or [], ensure_ascii=False),
                summary or "",
            ),
        )
        # 每个用户只保留最近 20 个版本，避免无限增长
        conn.execute(
            "DELETE FROM learning_path_versions WHERE user_id = ? AND version <= ?",
            (user_id, max(0, version - 20)),
        )
        conn.commit()
        return version
    finally:
        conn.close()


def _load_path_versions(user_id: int, limit: int = 5) -> list:
    """读取最近的路径版本，供前端展示「路线变更记录」。"""
    if not _ensure_path_versions_table():
        return []
    conn = get_db()
    try:
        rows = conn.execute(
            """SELECT version, trigger, trigger_label, reason_json, diff_json, summary, created_at
               FROM learning_path_versions WHERE user_id = ?
               ORDER BY version DESC LIMIT ?""",
            (user_id, limit),
        ).fetchall()
    except Exception:
        return []
    finally:
        conn.close()

    history = []
    for row in rows:
        diff = json_load(row["diff_json"]) or {}
        reason = json_load(row["reason_json"]) or {}
        history.append({
            "version": row["version"],
            "trigger": row["trigger"],
            "trigger_label": row["trigger_label"],
            "summary": row["summary"],
            "reason": reason,
            "diff": diff,
            "counts": diff.get("counts") or {},
            "created_at": row["created_at"],
        })
    return history


async def _replan_course_path(user_id: int, trigger: str = "manual",
                              trigger_label: str = "手动重排", reason: dict = None,
                              session_id: int = None) -> dict:
    """重新编排项目制学习路径，并记录版本快照与变更原因（#45）。

    迁移规则：按 (知识点, 实验, 主题) 这个稳定键匹配旧任务（重排只会改 day，不会改这三项），
    保留 learn/quiz/code 三个子项状态；新增的补先修任务从零开始，不会覆盖任何已有完成记录。
    """
    from services.agent_course import TRACK_NAMES, plan_course_path

    path = await get_learning_path(user_id)
    if not path:
        raise ValueError("还没有学习路径，请先生成路径")

    path_data = path.get("path_data") or {}
    progress = path.get("progress") or {}
    old_completed = progress.get("completed_tasks") or {}
    old_snapshot = _path_snapshot(path_data, progress)

    # 稳定键索引：重排后 day 会变，用知识点 + 实验 + 主题定位同一个任务
    old_status_by_identity = {}
    old_status_by_topic = {}
    for phase in path_data.get("phases", []):
        if phase.get("personalized_review"):
            continue
        for task in phase.get("tasks", []):
            topic = task.get("topic")
            status = old_completed.get(_get_task_key(task.get("day", 0), topic or "")) or {}
            if topic and any(status.get(k) for k in ("learn", "quiz", "code")):
                snapshot = {
                    "learn": bool(status.get("learn")),
                    "quiz": bool(status.get("quiz")),
                    "code": bool(status.get("code")),
                }
                old_status_by_identity[_task_identity(task)] = snapshot
                old_status_by_topic.setdefault(topic, snapshot)

    selected = [
        phase.get("name") for phase in path_data.get("phases", [])
        if not phase.get("personalized_review") and phase.get("name") in TRACK_NAMES
    ]
    if not selected:
        selected = [name for name in TRACK_NAMES if name in set(path_data.get("modules_selected") or [])]
    if not selected:
        selected = list(TRACK_NAMES)

    level_profile = dict(path_data.get("level_profile") or {})
    # 用当前掌握度覆盖生成时的快照：应用图谱时要按「现在学到哪了」重排，而不是旧数据
    mastery_detail = _mastery_detail_by_knowledge(user_id)
    current_mastery = {tag: item["score"] for tag, item in mastery_detail.items()}
    if current_mastery:
        merged_mastery = dict(level_profile.get("mastery") or {})
        merged_mastery.update(current_mastery)
        level_profile["mastery"] = merged_mastery
    learning_depth = path_data.get("learning_depth") or "标准"
    graph_context = _build_graph_context(user_id, level_profile.get("mastery"), mastery_detail)
    new_path = plan_course_path(
        selected,
        level_profile,
        learning_depth,
        prereq_map=graph_context["prereq_map"],
        graph_context=graph_context,
    )

    total_tasks = 0
    completed_count = 0
    migrated_topics = []
    new_completed = {}
    for phase in new_path["phases"]:
        for task in phase["tasks"]:
            total_tasks += 1
            key = _get_task_key(task["day"], task["topic"])
            status = old_status_by_identity.get(_task_identity(task)) \
                or old_status_by_topic.get(task["topic"])
            if status:
                new_completed[key] = status
                migrated_topics.append(task["topic"])
            else:
                new_completed[key] = {"learn": False, "quiz": False, "code": False}
            if _is_task_fully_complete(new_completed[key]):
                completed_count += 1

    days = [task["day"] for phase in new_path["phases"] for task in phase["tasks"]]
    current_day = next(
        (
            task["day"] for phase in new_path["phases"] for task in phase["tasks"]
            if not _is_task_fully_complete(
                new_completed.get(_get_task_key(task["day"], task["topic"]), {})
            )
        ),
        max(days) if days else 1,
    )

    # 保留 task_quiz_map / used_question_texts 等辅助键，避免重排后在途测评记录丢失
    new_progress = dict(progress or {})
    new_progress.update({
        "completed_tasks": new_completed,
        "overall_progress": round(completed_count / total_tasks * 100) if total_tasks else 0,
        "current_day": current_day,
        "remedial_tasks": {},
    })

    conn = get_db()
    try:
        conn.execute(
            "UPDATE learning_paths SET path_data_json = ?, progress_json = ?, updated_at = ? WHERE id = ?",
            (
                json.dumps(new_path, ensure_ascii=False),
                json.dumps(new_progress, ensure_ascii=False),
                datetime.now().isoformat(),
                path["id"],
            ),
        )
        conn.commit()
    finally:
        conn.close()

    # ── 版本快照与差异（#45）──
    new_snapshot = _path_snapshot(new_path, new_progress)
    diff = _diff_path_snapshots(old_snapshot, new_snapshot)
    changes = (reason or {}).get("mastery_changes") or []
    summary = _describe_replan(trigger_label, changes, diff)
    full_reason = {
        "trigger": trigger,
        "trigger_label": trigger_label,
        "session_id": session_id,
        "mastery_changes": changes,
    }

    # 第一次重排时补一条「生成时的初始路线」基线，方便对比第一版改了什么
    if not _load_path_versions(user_id, limit=1):
        _record_path_version(
            user_id,
            path["id"],
            trigger="baseline",
            trigger_label="初始路线",
            reason={"note": "生成学习路线时的基线，用于对比后续每次调整"},
            diff={},
            snapshot=old_snapshot,
            summary="生成学习路线时的初始版本",
        )
    version = _record_path_version(
        user_id,
        path["id"],
        trigger=trigger,
        trigger_label=trigger_label,
        reason=full_reason,
        diff=diff,
        snapshot=new_snapshot,
        summary=summary,
    )

    graph_operator = (new_path.get("applied_operators") or {}).get("graph") or {}
    return {
        "path_data": new_path,
        "progress": new_progress,
        "migrated_count": len(migrated_topics),
        "migrated_topics": migrated_topics,
        "graph": {
            "has_graph": graph_context["has_graph"],
            "source": graph_context["source"],
            "merged_edges": len(graph_context.get("added_edges") or []),
            "remedial_inserted": len(graph_operator.get("remedial_inserted") or []),
            "skip_blocked": len(graph_operator.get("skip_blocked") or []),
            "readiness_blocked": len(graph_operator.get("readiness_blocked") or []),
        },
        "personalization_summary": new_path.get("personalization_summary", ""),
        "version": version,
        "version_summary": summary,
        "diff": diff,
        "changes": changes,
    }


async def apply_graph_to_path(user_id: int) -> dict:
    """把当前知识图谱重新应用到学习路径：重新编排并迁移已有进度。

    使用场景：用户刚生成或重新生成知识图谱，旧路径是在没有图谱时生成的。
    迁移规则见 _replan_course_path。
    """
    return await _replan_course_path(
        user_id,
        trigger="graph",
        trigger_label="按知识图谱重排",
        reason={"mastery_changes": []},
    )


async def maybe_auto_replan_after_assessment(user_id: int, trigger: str,
                                             trigger_label: str,
                                             session_id: int = None) -> dict:
    """测评/实验产生新证据后，自动判断是否需要重排路线（#45）。

    只有「掌握度发生了有意义变化」才重排，避免每做一道题就把路线翻一遍：
    - 任一知识点分数变化 ≥ 0.1；
    - 或跨越 40% / 70% 分档；
    - 或路径里原本没有记录、现在有了新的练习证据。
    """
    from services.agent_course import COURSE_TRACKS, TRACK_NAMES, course_point_names

    path = await get_learning_path(user_id)
    if not path:
        return {
            "applied": False,
            "reason": "no_path",
            "message": "还没有学习路径，先做测评生成路线。",
        }

    path_data = path.get("path_data") or {}
    phase_names = {
        phase.get("name") for phase in path_data.get("phases", [])
        if not phase.get("personalized_review")
    }
    if not phase_names.intersection(TRACK_NAMES):
        return {
            "applied": False,
            "reason": "not_course_path",
            "message": "当前路径不是项目制课程路线，暂不自动重排。",
        }

    old_mastery = dict((path_data.get("level_profile") or {}).get("mastery") or {})
    try:
        detail = _mastery_detail_by_knowledge(user_id)
    except Exception:
        detail = {}

    course_tags = {
        task.get("knowledge")
        for track in COURSE_TRACKS
        for task in track["tasks"]
        if task.get("knowledge")
    }
    changes = [
        item for item in _mastery_changes(old_mastery, detail)
        if item.get("knowledge") in course_tags
    ]
    if changes:
        name_map = course_point_names()
        for item in changes:
            item["name"] = name_map.get(item["knowledge"]) or item["knowledge"]
    if not changes:
        return {
            "applied": False,
            "reason": "no_significant_change",
            "message": "掌握度变化还不明显，路线暂时不用调整。",
            "changes": [],
        }

    try:
        result = await _replan_course_path(
            user_id,
            trigger=trigger,
            trigger_label=trigger_label,
            reason={"mastery_changes": changes},
            session_id=session_id,
        )
    except Exception as exc:
        print(f"[auto_replan] 自动重排失败: {exc}")
        return {
            "applied": False,
            "reason": "replan_failed",
            "message": f"路线自动调整失败：{exc}",
            "changes": changes,
        }

    return {
        "applied": True,
        "reason": "mastery_changed",
        "message": result.get("version_summary") or "已按最新掌握度自动调整路线。",
        "version": result.get("version"),
        "diff": result.get("diff") or {},
        "changes": changes,
        "migrated_count": result.get("migrated_count", 0),
    }


async def list_path_versions(user_id: int, limit: int = 10) -> list:
    """查询路径版本历史（最近 limit 条）。"""
    return _load_path_versions(user_id, limit=limit)


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


def _task_identity(task: dict) -> str:
    """跨重排稳定的任务标识：知识点 + 实验模块 + 主题。"""
    return "|".join(str(task.get(k) or "") for k in ("knowledge", "lab_id", "topic"))


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
            {"topic": "线性结构与算法基础巩固", "knowledge": "线性结构", "action": "复习数据结构核心内容，做好笔记", "resource": "课程讲义/课件", "check": "能用自己的话解释核心概念"},
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
        return ["算法工具箱与综合"]

    # 按关键词长度降序匹配（"哈希与缓存" > "哈希"），累加权重
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
    return ["算法工具箱与综合"]


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
        "线性结构": "线性结构",
        "树与堆": "树与堆",
        "图与并查集": "图与并查集",
        "排序算法": "排序算法",
        "哈希与缓存": "哈希与缓存",
        "算法工具箱与综合": "算法工具箱与综合",
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
