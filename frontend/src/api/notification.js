import request from './request'

/** 站内提醒（#32）：列表（含未读数与开关状态，会按当日幂等生成） */
export const getNotifications = (params) => request.get('/notifications', { params })

/** 标记单条已读 */
export const markNotificationRead = (id) => request.post(`/notifications/${id}/read`)

/** 全部标为已读 */
export const markAllNotificationsRead = () => request.post('/notifications/read-all')

/** 读取每日提醒开关 */
export const getReminderSettings = () => request.get('/notifications/settings')

/** 更新每日提醒开关 */
export const updateReminderSettings = (reminderEnabled) =>
  request.put('/notifications/settings', { reminder_enabled: reminderEnabled })
