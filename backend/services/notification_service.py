"""站内提醒服务（#32 最小可用提醒体系）。

定位：只做"最小可用"的站内提醒，不做站外推送（邮件/企微）。应用打开时拉取，
按当日幂等生成三类通知：
- review：今日待复习（`knowledge_mastery` 中到期未复习的薄弱证据）
- streak：连续未学习（依据 `learning_stats` 的连续学习天数/最近学习日）
- api_config：API Key 未配置（常驻提醒，见下方说明）

每条通知按 category + 当日 去重，重复拉取不会重复插行；用户可在个人中心关闭
"每日学习提醒"（`users.reminder_enabled`），关闭后不再生成新通知。

例外：api_config 是**常驻提醒**——不受"每日学习提醒"开关影响，也不能被标记
已读或隐藏；只有把 5 个 Key 全部配置好，后端才会自动删除这条提醒。
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

from database import get_db
from services.secret_store import decrypt_config

CATEGORY_REVIEW = "review"
CATEGORY_STREAK = "streak"
CATEGORY_API_CONFIG = "api_config"

# 常驻提醒：不可标记已读、不可隐藏，条件解除后由后端自动删除
STICKY_CATEGORIES = {CATEGORY_API_CONFIG}

# 需要用户自行配置的 API Key（字段名 → 给人看的名字）
_API_KEY_ITEMS = (
    ("api_key", "对话模型 Key（DeepSeek）"),
    ("embedding_api_key", "知识库嵌入 Key（SiliconFlow）"),
    ("search_api_key", "联网搜索 Key（Tavily）"),
    ("jev_api_key", "意图判定 Key（OpenRouter）"),
)

# 连续未学习提醒阈值（天）：最近一次学习距今 >= 该值即提醒
STREAK_ALERT_DAYS = 2


def _today() -> date:
    return date.today()


def _iso(d) -> str:
    return d.isoformat() if isinstance(d, date) else str(d)[:10]


# ── 提醒开关 ──────────────────────────────────────────────

def _get_reminder_enabled(conn, user_id: int) -> bool:
    row = conn.execute(
        "SELECT reminder_enabled FROM users WHERE id = ?", (user_id,)
    ).fetchone()
    if row is None:
        return True
    val = row["reminder_enabled"]
    return True if val is None else bool(int(val))


def set_reminder_enabled(user_id: int, enabled: bool) -> bool:
    conn = get_db()
    conn.execute(
        "UPDATE users SET reminder_enabled = ?, updated_at = ? WHERE id = ?",
        (1 if enabled else 0, datetime.now().isoformat(), user_id),
    )
    conn.commit()
    conn.close()
    return bool(enabled)


# ── 计数/统计 ─────────────────────────────────────────────

def _count_due_review(conn, user_id: int) -> int:
    """与 personalization_service.get_due_review_recommendations 同口径的到期薄弱证据数。"""
    row = conn.execute(
        """SELECT COUNT(*) AS c FROM knowledge_mastery
           WHERE user_id = ? AND mastery_score < 0.65
             AND date(last_activity_at) < date('now')
             AND (next_review_at IS NULL OR date(next_review_at) <= date('now'))""",
        (user_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0


def get_study_streak(conn, user_id: int) -> tuple[int, str | None]:
    """连续学习天数（含今日或截至昨日）与最近学习日。

    统计口径包含两类行为，任一发生即算当天有学习：
    - `learning_stats`：有学习时长或做题数
    - `learning_records`：页面访问、错题复习等学习动作
    今天尚未学习时从昨天起算，避免上午打开应用就"断签"。
    """
    rows = conn.execute(
        """SELECT DISTINCT d FROM (
               SELECT date AS d FROM learning_stats
                 WHERE user_id = ? AND (study_duration > 0 OR questions_done > 0)
               UNION
               SELECT date(created_at) AS d FROM learning_records
                 WHERE user_id = ?
           )
           WHERE d IS NOT NULL
           ORDER BY d DESC LIMIT 400""",
        (user_id, user_id),
    ).fetchall()
    days = {_iso(r["d"]) for r in rows if r["d"]}
    if not days:
        return 0, None
    cursor = _today()
    if cursor.isoformat() not in days:
        cursor = cursor - timedelta(days=1)
    streak = 0
    while cursor.isoformat() in days:
        streak += 1
        cursor -= timedelta(days=1)
    return streak, max(days)


def _notification_exists_today(conn, user_id: int, category: str) -> bool:
    row = conn.execute(
        """SELECT id FROM notifications
           WHERE user_id = ? AND category = ? AND date(created_at) = date('now')
           LIMIT 1""",
        (user_id, category),
    ).fetchone()
    return row is not None


def _insert_notification(conn, user_id: int, category: str, title: str, content: str, action_url: str) -> None:
    conn.execute(
        """INSERT INTO notifications (user_id, category, title, content, action_url, is_read)
           VALUES (?, ?, ?, ?, ?, 0)""",
        (user_id, category, title, content, action_url),
    )


def _missing_api_keys(conn, user_id: int) -> list[str]:
    """返回尚未配置的 Key 名称（按 _API_KEY_ITEMS 顺序）。"""
    row = conn.execute(
        """SELECT api_key, embedding_api_key, search_api_key, jev_api_key
           FROM user_llm_config WHERE user_id = ?""",
        (user_id,),
    ).fetchone()
    config = decrypt_config(dict(row)) if row else {}
    return [
        label for field, label in _API_KEY_ITEMS
        if not str((config or {}).get(field) or "").strip()
    ]


def _sync_api_config_notice(conn, user_id: int) -> None:
    """同步「API Key 未配置」常驻提醒：缺 Key 就创建/更新，配齐就自动删除。

    不只按当日去重，而是全表只保留一条：内容随缺失项变化而更新，
    且始终重置为未读，保证它在横幅上一直可见、无法被"已读"掉。
    """
    missing = _missing_api_keys(conn, user_id)
    row = conn.execute(
        """SELECT id FROM notifications
           WHERE user_id = ? AND category = ? ORDER BY id DESC LIMIT 1""",
        (user_id, CATEGORY_API_CONFIG),
    ).fetchone()

    if not missing:
        if row:
            conn.execute(
                "DELETE FROM notifications WHERE user_id = ? AND category = ?",
                (user_id, CATEGORY_API_CONFIG),
            )
            conn.commit()
        return

    title = f"还有 {len(missing)} 项 API Key 未配置"
    content = "未配置：" + "、".join(missing) + "。到个人中心配置后才能使用对应功能。"
    if row:
        conn.execute(
            """UPDATE notifications
                  SET title = ?, content = ?, action_url = ?, is_read = 0
                WHERE id = ?""",
            (title, content, "/profile", row["id"]),
        )
    else:
        _insert_notification(conn, user_id, CATEGORY_API_CONFIG, title, content, "/profile")
    conn.commit()


def generate_notifications(conn, user_id: int) -> list[dict]:
    """按当日幂等生成提醒，返回本次新生成的通知列表。"""
    # 常驻提醒不受「每日学习提醒」开关影响：只要还有 Key 没配就一直挂着
    _sync_api_config_notice(conn, user_id)

    if not _get_reminder_enabled(conn, user_id):
        return []

    created: list[dict] = []

    due = _count_due_review(conn, user_id)
    if due > 0 and not _notification_exists_today(conn, user_id, CATEGORY_REVIEW):
        title = "今日待复习"
        content = f"你有 {due} 个知识点到了复习时间，去错题本巩固一下吧。"
        _insert_notification(conn, user_id, CATEGORY_REVIEW, title, content, "/error-book")
        created.append({"category": CATEGORY_REVIEW, "title": title, "content": content, "action_url": "/error-book"})

    streak, last_active = get_study_streak(conn, user_id)
    if last_active:
        days_since = (_today() - date.fromisoformat(last_active)).days
        if days_since >= STREAK_ALERT_DAYS:
            if not _notification_exists_today(conn, user_id, CATEGORY_STREAK):
                title = "学习提醒"
                content = f"你已连续 {days_since} 天没有学习记录，回来继续吧。"
                _insert_notification(conn, user_id, CATEGORY_STREAK, title, content, "/dashboard")
                created.append({"category": CATEGORY_STREAK, "title": title, "content": content, "action_url": "/dashboard"})
                conn.commit()
        else:
            # 用户已经学习过，“多久没学习”的提醒不再成立。连同历史已读的一起清掉，
            # 否则列表里还留着「你已连续 N 天没有学习记录」，用户会以为系统没算他的复习。
            conn.execute(
                """DELETE FROM notifications
                   WHERE user_id = ? AND category = ?""",
                (user_id, CATEGORY_STREAK),
            )
            conn.commit()

    if created:
        conn.commit()
    return created


# ── 读取 / 已读 ───────────────────────────────────────────

def list_notifications(user_id: int, limit: int = 20) -> dict:
    """拉取通知（先按当日幂等生成，再返回列表 + 未读数 + 开关状态）。

    常驻提醒排在最前，并带 ``sticky=True``，前端据此不给"关闭"按钮。
    """
    conn = get_db()
    try:
        generate_notifications(conn, user_id)
        rows = conn.execute(
            """SELECT id, category, title, content, action_url, is_read, created_at
               FROM notifications WHERE user_id = ?
               ORDER BY CASE WHEN category = ? THEN 0 ELSE 1 END, id DESC
               LIMIT ?""",
            (user_id, CATEGORY_API_CONFIG, max(1, min(limit, 100))),
        ).fetchall()
        unread_row = conn.execute(
            "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
            (user_id,),
        ).fetchone()
        items = [dict(r) for r in rows]
        for it in items:
            it["is_read"] = bool(int(it.get("is_read") or 0))
            it["sticky"] = it.get("category") in STICKY_CATEGORIES
        return {
            "items": items,
            "unread_count": int(unread_row["c"] or 0) if unread_row else 0,
            "reminder_enabled": _get_reminder_enabled(conn, user_id),
        }
    finally:
        conn.close()


def mark_read(user_id: int, notification_id: int) -> int:
    conn = get_db()
    try:
        row = conn.execute(
            "SELECT category FROM notifications WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        ).fetchone()
        # 常驻提醒不允许被"已读"掉，未读数保持不减
        if row is None or row["category"] in STICKY_CATEGORIES:
            return get_unread_count(conn, user_id)
        conn.execute(
            "UPDATE notifications SET is_read = 1 WHERE id = ? AND user_id = ?",
            (notification_id, user_id),
        )
        conn.commit()
        return get_unread_count(conn, user_id)
    finally:
        conn.close()


def mark_all_read(user_id: int) -> int:
    conn = get_db()
    try:
        placeholders = ", ".join("?" for _ in STICKY_CATEGORIES)
        conn.execute(
            f"""UPDATE notifications SET is_read = 1
                 WHERE user_id = ? AND is_read = 0
                   AND category NOT IN ({placeholders})""",
            (user_id, *sorted(STICKY_CATEGORIES)),
        )
        conn.commit()
        return get_unread_count(conn, user_id)
    finally:
        conn.close()


def get_unread_count(conn, user_id: int) -> int:
    row = conn.execute(
        "SELECT COUNT(*) AS c FROM notifications WHERE user_id = ? AND is_read = 0",
        (user_id,),
    ).fetchone()
    return int(row["c"] or 0) if row else 0
