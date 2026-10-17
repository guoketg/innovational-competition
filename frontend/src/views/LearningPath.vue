<template>
  <div class="learning-path-page">
    <PageHero
      eyebrow="PERSONALIZED PATH"
      title="学习路线图"
      description="依赖图约束下的个性化编排：每个站点按你的掌握度着色，连线表示先修依赖，箭头方向即建议的学习顺序。"
      icon="Guide"
    >
      <template #meta>
        <el-tag v-if="summary.total_stations" effect="plain" size="small">共 {{ summary.total_stations }} 站 · 已完成 {{ summary.completed_stations }} 站</el-tag>
        <el-tag v-if="summary.current_station_topic" type="warning" effect="plain" size="small">当前位置：{{ summary.current_station_topic }}</el-tag>
        <el-tag v-if="knowledgeStats.total" effect="plain" size="small">知识点已掌握 {{ knowledgeStats.mastered || 0 }} / {{ knowledgeStats.total }}</el-tag>
        <el-tag v-if="learningDepth" type="info" effect="plain" size="small">{{ learningDepth }}</el-tag>
      </template>
      <template #actions>
        <el-button size="small" @click="openPreferenceDialog">目标与预算</el-button>
        <el-button size="small" :loading="loading" @click="load">刷新</el-button>
        <el-button v-if="hasPath" size="small" :loading="regenerating" @click="regeneratePath">重新生成</el-button>
        <el-button size="small" type="primary" @click="router.push('/code-lab')">去编程实验室</el-button>
      </template>
    </PageHero>

    <el-empty
      v-if="!loading && !hasPath"
      description="还没有学习路径。先做 5 道小测评，我会按你的水平调整路线；也可以跳过，先按默认水平生成。"
    >
      <div class="empty-actions">
        <el-button type="primary" :loading="generating" @click="openQuickQuiz">先做 5 题测评（约 3 分钟）</el-button>
        <el-button :loading="generating" @click="generatePath()">跳过测评，直接生成</el-button>
      </div>
    </el-empty>

    <el-dialog
      v-model="quizVisible"
      :title="quizTitle"
      width="640px"
      :close-on-click-modal="false"
    >
      <p class="quiz-hint">{{ quizHint }}</p>
      <div v-if="quizLoading" v-loading="true" class="quiz-loading"></div>
      <template v-else>
        <article v-for="(q, qi) in quizQuestions" :key="q.question_id" class="quiz-item">
          <h4>{{ qi + 1 }}. {{ q.question }}</h4>
          <div v-if="q.options && q.options.length">
            <el-radio-group
              v-if="q.question_type === '单选' || q.question_type === '读代码' || q.question_type === '判断'"
              v-model="quizAnswers[q.question_id]"
            >
              <el-radio v-for="(opt, oi) in q.options" :key="oi" :value="opt">{{ opt }}</el-radio>
            </el-radio-group>
            <el-checkbox-group v-else-if="q.question_type === '多选'" v-model="quizMultiAnswers[q.question_id]">
              <el-checkbox v-for="(opt, oi) in q.options" :key="oi" :value="opt">{{ opt }}</el-checkbox>
            </el-checkbox-group>
          </div>
          <el-input
            v-else
            v-model="quizAnswers[q.question_id]"
            type="textarea"
            :rows="2"
            placeholder="请输入你的答案；不会可以留空"
          />
        </article>
      </template>
      <template #footer>
        <el-button @click="quizVisible = false">取消</el-button>
        <el-button v-if="quizMode === 'placement'" :loading="generating" @click="generatePath()">跳过测评，直接生成</el-button>
        <el-button type="primary" :loading="quizSubmitting" @click="submitQuickQuiz">
          {{ quizMode === 'diagnose' ? '提交，更新掌握度' : '提交并生成路线' }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog
      v-model="preferenceVisible"
      title="目标与预算"
      width="560px"
      :close-on-click-modal="false"
    >
      <p class="pref-hint">
        告诉系统你想学到哪、每周能花多少时间，路线会优先安排这些目标，并把总量压进你的时间预算。
      </p>
      <el-form label-width="110px" label-position="left">
        <el-form-item label="目标知识点">
          <el-select
            v-model="preferenceForm.target_tags"
            multiple
            filterable
            clearable
            collapse-tags
            collapse-tags-tooltip
            placeholder="不选则按课程顺序推进"
            class="pref-select"
          >
            <el-option
              v-for="unit in targetOptions"
              :key="unit.tag"
              :label="unit.name"
              :value="unit.tag"
            />
          </el-select>
        </el-form-item>
        <el-form-item label="每周可投入">
          <el-input-number v-model="preferenceForm.weekly_hours" :min="1" :max="40" :step="1" />
          <span class="pref-unit">小时 / 周</span>
        </el-form-item>
        <el-form-item label="完成期限">
          <el-input-number v-model="preferenceForm.deadline_weeks" :min="1" :max="52" :step="1" />
          <span class="pref-unit">周内完成</span>
        </el-form-item>
        <el-form-item label="编排偏好">
          <el-radio-group v-model="preferenceForm.preferred_mode">
            <el-radio-button value="">自动推荐</el-radio-button>
            <el-radio-button value="均衡">均衡</el-radio-button>
            <el-radio-button value="补弱优先">补弱优先</el-radio-button>
            <el-radio-button value="目标优先">目标优先</el-radio-button>
            <el-radio-button value="省时优先">省时优先</el-radio-button>
          </el-radio-group>
        </el-form-item>
      </el-form>
      <p class="pref-note">
        应用后路线会按新设置重新编排；已完成的任务进度会保留，不会清零。
      </p>
      <template #footer>
        <el-button @click="preferenceVisible = false">取消</el-button>
        <el-button :loading="generating" @click="savePreferences(false)">仅保存</el-button>
        <el-button type="primary" :loading="generating" @click="savePreferences(true)">
          保存并重新编排
        </el-button>
      </template>
    </el-dialog>

    <template v-if="loading || hasPath">
      <div class="view-switch">
        <button
          v-for="tab in VIEWS"
          :key="tab.key"
          :class="['view-tab', { active: viewMode === tab.key }]"
          @click="switchView(tab.key)"
        >{{ tab.label }}</button>
      </div>

      <template v-if="viewMode === 'roadmap'">
      <section v-if="reviewNotice" class="notice-strip">
        <span class="notice-dot"></span>
        <div>
          <strong>{{ reviewNotice.title || '检测到需要返工的知识点' }}</strong>
          <p>{{ reviewNotice.message }}</p>
        </div>
      </section>

      <section v-if="graphImpact.has_graph" class="graph-impact-strip">
        <div class="impact-copy">
          <b>知识图谱正在参与路线编排</b>
          <span>先修关系不只画在图上：AI 补出的先修边会改变学习顺序，前置没打牢的知识点会被拦下快进。</span>
          <ul v-if="graphImpact.remedial_links?.length" class="impact-links">
            <li v-for="link in graphImpact.remedial_links" :key="`${link.day}-${link.topic}`">
              第 {{ link.day }} 天「{{ link.topic }}」先补 <b>{{ link.blocker_name }}</b>
            </li>
          </ul>
        </div>
        <div class="impact-metrics">
          <span>AI 补充先修 <b>{{ graphImpact.merged_edges || 0 }}</b> 条</span>
          <span>插入/关联补先修 <b>{{ graphImpact.remedial_stations || 0 }}</b> 个</span>
          <span>拦下超前快进 <b>{{ pathSkipBlocked }}</b> 个</span>
          <span>被前置卡住 <b>{{ graphImpact.blocked_stations || 0 }}</b> 站</span>
          <span v-if="graphImpact.undiagnosed_stations">未诊断前置 <b>{{ graphImpact.undiagnosed_stations }}</b> 站</span>
        </div>
        <el-button size="small" text type="primary" @click="switchView('graph')">查看知识图谱 →</el-button>
      </section>

      <section v-if="counterfactual?.available" class="counterfactual-card">
        <header class="cf-head">
          <div>
            <h2>{{ counterfactual.question }}</h2>
            <p>假设你把这个前置补到 95% 掌握，再重新排一遍路线。只是推演，不会改动你的学习记录。</p>
          </div>
          <el-tag size="small" type="success" effect="plain">
            当前被卡住 {{ counterfactual.baseline?.locked_count || 0 }} 个知识点
          </el-tag>
        </header>
        <ul class="cf-options">
          <li
            v-for="(item, index) in counterfactual.options"
            :key="item.tag"
            :class="['cf-item', { best: index === 0 }]"
          >
            <span class="cf-rank">{{ index === 0 ? '最划算' : `第 ${index + 1} 选` }}</span>
            <div class="cf-main">
              <div class="cf-name">
                <b>{{ item.name }}</b>
                <em v-if="item.module">{{ item.module }}</em>
              </div>
              <p>{{ item.reason }}</p>
            </div>
            <div class="cf-metrics">
              <span v-if="item.unlocked_count">解锁 <b>{{ item.unlocked_count }}</b> 个</span>
              <span v-if="item.unlocked_minutes">解锁内容约 <b>{{ formatMinutes(item.unlocked_minutes) }}</b></span>
              <span v-if="item.unlocked_weeks">≈ <b>{{ item.unlocked_weeks }}</b> 周学时</span>
              <span v-if="item.minutes_saved > 0">整体省 <b>{{ formatMinutes(item.minutes_saved) }}</b></span>
              <span v-if="item.weeks_saved">≈ 提前 <b>{{ item.weeks_saved }}</b> 周</span>
              <span class="cf-cost">先投入 {{ formatMinutes(item.study_minutes) }}</span>
            </div>
          </li>
        </ul>
        <p class="cf-note">
          {{ counterfactual.assumption }}
          <template v-if="!counterfactual.weekly_hours">你还没设置每周学习时长，所以只折算了分钟，没有折算成周。</template>
        </p>
      </section>

      <section class="summary-grid">
        <article class="summary-card">
          <small>路径总进度</small>
          <b>{{ summary.overall_progress || 0 }}%</b>
          <el-progress :percentage="summary.overall_progress || 0" :stroke-width="7" :show-text="false" />
        </article>
        <article class="summary-card">
          <small>已完成站点</small>
          <b>{{ summary.completed_stations || 0 }} / {{ summary.total_stations || 0 }}</b>
          <span>当前第 {{ summary.current_day || 1 }} 天</span>
        </article>
        <article class="summary-card">
          <small>待补强知识点</small>
          <b>{{ lowMasteryCount }}</b>
          <span>掌握度低于 40% 的站点</span>
        </article>
        <article class="summary-card">
          <small>可快进知识点</small>
          <b>{{ highMasteryCount }}</b>
          <span>掌握度已达 70% 以上</span>
        </article>
      </section>

      <section v-if="learnerProfile" class="profile-card">
        <header class="profile-head">
          <div>
            <h2>你的学习画像</h2>
            <p>路线不只看掌握度：目标、时间预算、偏好、错题和证据不足的知识点都会改变编排结果。</p>
          </div>
          <el-tag v-if="pathStrategy" type="success" effect="plain" size="small">
            当前编排：{{ pathStrategy.mode_label }}
          </el-tag>
        </header>
        <div class="profile-tags">
          <span v-if="learnerProfile.level_label" class="profile-chip">
            水平：<b>{{ learnerProfile.level_label }}</b>
          </span>
          <span v-if="learnerProfile.target_names?.length" class="profile-chip">
            目标：<b>{{ learnerProfile.target_names.join('、') }}</b>
          </span>
          <span v-if="learnerProfile.time_budget?.weekly_hours" class="profile-chip">
            每周 <b>{{ learnerProfile.time_budget.weekly_hours }}</b> 小时
          </span>
          <span v-if="learnerProfile.time_budget?.deadline_weeks" class="profile-chip">
            <b>{{ learnerProfile.time_budget.deadline_weeks }}</b> 周内完成
          </span>
          <span v-if="learnerProfile.preferences?.mode_label" class="profile-chip">
            偏好：<b>{{ learnerProfile.preferences.mode_label }}</b>
          </span>
          <span v-else class="profile-chip">偏好：<b>自动推荐</b></span>
        </div>
        <div class="profile-notes">
          <p>
            <b>错题画像：</b>
            <template v-if="learnerProfile.error_profile?.top_error_tags?.length">
              错得最多的是
              <em v-for="item in learnerProfile.error_profile.top_error_tags" :key="item.tag" class="profile-em">
                {{ item.name }}（{{ item.wrong }} 题）
              </em>
              ，这些知识点会被排到更前面。
            </template>
            <template v-else>还没有错题记录，路线先按整体掌握度推进。</template>
          </p>
          <p>
            <b>掌握度把握：</b>
            <template v-if="learnerProfile.mastery_uncertainty?.top_uncertain_tags?.length">
              有 {{ learnerProfile.mastery_uncertainty.top_uncertain_tags.length }} 个知识点证据不足（如
              {{ learnerProfile.mastery_uncertainty.top_uncertain_tags.slice(0, 3).map(item => item.name).join('、') }}），
              路线会先安排小测确认，避免估错水平。
            </template>
            <template v-else>每个知识点的掌握度都有足够练习证据支撑。</template>
          </p>
        </div>
      </section>

      <section v-if="pathAlternatives.length" class="alt-card">
        <header class="card-head">
          <div>
            <h2>其他编排方案</h2>
            <p>系统同时生成了几种路线，按先修阻塞、目标覆盖、薄弱补强、用时和难度平滑综合打分。选一条即可重新编排，进度保留。</p>
          </div>
        </header>
        <div class="alt-grid">
          <article v-for="alt in pathAlternatives" :key="alt.strategy" class="alt-item">
            <div class="alt-head">
              <b>{{ alt.mode_label }}</b>
              <el-tag v-if="alt.time_fit === false" type="warning" effect="plain" size="small">超预算</el-tag>
              <el-tag v-else-if="alt.time_fit === true" type="success" effect="plain" size="small">预算内</el-tag>
            </div>
            <ul class="alt-points">
              <li v-for="point in alt.highlights" :key="point">{{ point }}</li>
            </ul>
            <div class="alt-foot">
              <span>{{ alt.estimated_total_days ? '约 ' + alt.estimated_total_days + ' 天' : '' }}</span>
              <el-button size="small" type="primary" plain @click="useAlternative(alt)">用这条</el-button>
            </div>
          </article>
        </div>
      </section>

      <section v-loading="loading" class="map-card">
        <header class="card-head">
          <div>
            <h2>学习地图</h2>
            <p>横向为拓扑深度（越靠右越依赖前面的内容），纵向为同层站点；虚线是同知识点的连续项目。</p>
          </div>
          <div class="legend">
            <span v-for="(band, key) in BAND" :key="key" class="legend-item">
              <i :style="{ background: band.color }"></i>{{ band.label }}
            </span>
            <span class="legend-item"><i class="legend-ring current"></i>当前站</span>
            <span class="legend-item"><i class="legend-ring done"></i>已完成</span>
          </div>
        </header>
        <div class="map-scroll">
          <div ref="mapEl" class="map-canvas" :style="{ height: layout.height + 'px', minWidth: layout.width + 'px' }"></div>
        </div>
      </section>

      <section class="progress-card">
        <header class="card-head">
          <div>
            <h2>阶段进度</h2>
            <p>每个阶段完成了多少站，以及现在走到哪一站。</p>
          </div>
        </header>
        <article v-for="phase in phaseGroups" :key="phase.name" class="phase-block">
          <div class="phase-head">
            <b>{{ phase.name }}</b>
            <span>已完成 {{ phase.done }} / 共 {{ phase.total }} 站</span>
            <el-progress
              class="phase-bar"
              :percentage="phase.total ? Math.round(phase.done / phase.total * 100) : 0"
              :stroke-width="7"
              :show-text="false"
            />
          </div>
          <ul class="station-list">
            <li
              v-for="station in phase.stations"
              :key="station.key"
              :class="['station-row', `is-${station.status}`]"
            >
              <span class="station-day">第 {{ station.day }} 天</span>
              <span class="station-title">
                <b>{{ station.topic }}</b>
                <small v-if="station.graph_blockers?.length" class="station-blockers">前置薄弱：{{ station.graph_blockers.join('、') }}</small>
                <small v-else>{{ station.duration || '按需完成' }}</small>
              </span>
              <span class="station-tags">
                <em v-if="station.is_remedial" class="mini-tag remedial">补先修</em>
                <em v-if="station.graph_gated" class="mini-tag gated">图谱锁定</em>
                <em v-else-if="station.skippable" class="mini-tag skip">可快进</em>
              </span>
              <el-tag :color="BAND[station.mastery_band].color" effect="dark" size="small" class="band-tag">
                {{ BAND[station.mastery_band].label }}{{ station.mastery !== null ? ' ' + Math.round(station.mastery * 100) + '%' : '' }}
              </el-tag>
              <span class="station-sub">
                <i :class="{ on: station.sub_tasks.learn }">教程</i>
                <i :class="{ on: station.sub_tasks.code }">实验</i>
                <i :class="{ on: station.sub_tasks.quiz }">练习</i>
              </span>
              <span :class="['station-status', `is-${station.status}`]">{{ statusLabel(station) }}</span>
              <span class="station-actions">
                <el-button v-if="station.knowledge" size="small" text @click="goDoc(station)">看教程</el-button>
                <el-button v-if="station.lab_id" size="small" text type="primary" @click="goStation(station)">做实验</el-button>
              </span>
            </li>
          </ul>
        </article>
      </section>

      <section v-if="pathHistory.length" class="history-card">
        <header class="card-head">
          <div>
            <h2>路线变更记录</h2>
            <p>每次测评或实验让掌握度发生明显变化时，路线会自动调整。这里写清每一版改了哪一步、为什么改。</p>
          </div>
          <span class="history-count">最近 {{ pathHistory.length }} 次调整</span>
        </header>
        <ul class="history-list">
          <li v-for="item in pathHistory" :key="item.version" class="history-row">
            <div class="history-head">
              <b class="history-version">V{{ item.version }}</b>
              <span class="history-trigger">{{ item.trigger_label || '手动重排' }}</span>
              <time class="history-time">{{ formatHistoryTime(item.created_at) }}</time>
            </div>
            <p class="history-summary">{{ item.summary || '本次调整没有明显变化' }}</p>
            <div v-if="historyMasteryChanges(item).length" class="history-changes">
              <span v-for="change in historyMasteryChanges(item)" :key="change.knowledge" class="history-change">
                {{ change.name || nodeName(change.knowledge) }}{{ formatMasteryChange(change) }}
              </span>
            </div>
            <div v-if="historyDiffTags(item).length" class="history-diff">
              <em v-for="tag in historyDiffTags(item)" :key="tag">{{ tag }}</em>
            </div>
          </li>
        </ul>
      </section>
      </template>

      <section v-if="viewMode === 'graph'" v-loading="graphLoading" class="graph-card">
        <header class="card-head">
          <div>
            <h2>知识图谱 <small class="graph-scope">{{ graphScope === 'mine' ? '我的图谱 · 跟着学习进度生长' : '完整课程图谱 · 44 个知识点' }}</small></h2>
            <p v-if="graphScope === 'mine'">只显示和你有关的节点：当前路线上的知识点、你已经练过的，以及前置已经打牢、可以接着学的拓展节点。你学得越多，这张图会长出越多节点——不同人看到的节点集合不一样。颜色是你自己的掌握度。实线是先修关系：深灰来自课程先修表（专家维护，不可改），蓝绿是 AI 推断且已达标，橙色虚线是 AI 推断但还需要你确认。</p>
            <p v-else>这是整门课的 44 个知识点全图，全班看到的结构相同，颜色才是你自己的掌握度。切回「我的图谱」可以只看与你当前进度相关的部分。</p>
          </div>
          <div class="legend">
            <span v-for="(band, key) in BAND" :key="key" class="legend-item">
              <i :style="{ background: band.color }"></i>{{ band.label }}
            </span>
            <span class="legend-item"><i class="legend-line expert"></i>专家先修</span>
            <span class="legend-item"><i class="legend-line ai"></i>AI 已采纳</span>
            <span class="legend-item"><i class="legend-line pending"></i>AI 待审核</span>
            <span class="legend-item"><i class="legend-line similar"></i>相似</span>
            <span class="legend-item"><i class="legend-line part-of"></i>包含（目录层级）</span>
            <span class="legend-item"><i class="legend-ring current"></i>当前站</span>
            <span class="legend-item"><i class="legend-ring done"></i>已完成</span>
            <span class="legend-item"><i class="legend-ring frontier"></i>可拓展</span>
          </div>
        </header>

        <div class="graph-bar">
          <el-radio-group v-model="graphScope" size="small" @change="changeGraphScope">
            <el-radio-button value="mine">我的图谱</el-radio-button>
            <el-radio-button value="full">完整课程图谱</el-radio-button>
          </el-radio-group>
          <el-button
            size="small"
            type="primary"
            :loading="graphGenerating"
            @click="generateGraph"
          >{{ graph?.has_graph ? '重新生成知识图谱' : '用 AI 构建知识图谱' }}</el-button>
          <el-tag size="small" effect="plain" :type="graph?.has_graph ? 'success' : 'info'">
            {{ graph?.has_graph ? 'AI 已生成' : '专家骨架' }}
          </el-tag>
          <el-radio-group v-model="edgeFilter" size="small" @change="renderActive">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="expert">仅专家</el-radio-button>
            <el-radio-button value="ai">仅 AI</el-radio-button>
            <el-radio-button value="pending">待审核</el-radio-button>
          </el-radio-group>
          <el-tag v-if="graphStats.nodes" size="small" effect="plain">知识点 {{ graphStats.nodes }}</el-tag>
          <el-tag v-if="graphScope === 'mine' && graphView.visible_nodes" size="small" type="success" effect="plain">
            本图 {{ graphView.visible_nodes }} 个
          </el-tag>
          <el-tag v-if="graphScope === 'mine' && graphView.hidden_nodes" size="small" type="info" effect="plain">
            另有 {{ graphView.hidden_nodes }} 个尚未解锁
          </el-tag>
          <el-tag v-if="graphScope === 'mine' && graphView.state_counts?.frontier" size="small" effect="plain">
            可拓展 {{ graphView.state_counts.frontier }}
          </el-tag>
          <el-tag v-if="graphStats.prerequisite" size="small" effect="plain">先修 {{ graphStats.prerequisite }}</el-tag>
          <el-tag v-if="graphStats.similar" size="small" effect="plain">相似 {{ graphStats.similar }}</el-tag>
          <el-tag v-if="graphStats.part_of" size="small" effect="plain">包含 {{ graphStats.part_of }}</el-tag>
          <el-tag v-if="graphStats.pending_edges" size="small" type="warning" effect="plain">
            待审核 {{ graphStats.pending_edges }} 条
          </el-tag>
          <el-tag v-if="graphDiscarded.length" size="small" type="info" effect="plain">
            已丢弃 {{ graphDiscarded.length }} 条无效关系
          </el-tag>
          <el-button
            v-if="graph?.path_needs_apply"
            size="small"
            type="success"
            :loading="graphApplying"
            @click="applyGraphToPath"
          >用图谱重排学习路径</el-button>
          <el-button size="small" type="warning" plain @click="openEvaluation">图谱测评</el-button>
          <el-button size="small" plain @click="openVersions">版本历史</el-button>
          <span class="graph-tip">拖动画布 · 点击节点查看详情</span>
        </div>

        <section class="graph-query">
          <div class="gq-row">
            <span class="gq-label">查邻居</span>
            <el-input
              v-model="neighborRef"
              size="small"
              class="gq-input"
              placeholder="知识点名称或 tag，如 二叉树"
              clearable
              @keyup.enter="queryNeighbors"
            />
            <el-select v-model="neighborHops" size="small" style="width: 88px">
              <el-option v-for="n in [1, 2, 3]" :key="n" :label="`${n} 跳`" :value="n" />
            </el-select>
            <el-select v-model="neighborDirection" size="small" style="width: 120px">
              <el-option label="两个方向" value="both" />
              <el-option label="只看后继" value="out" />
              <el-option label="只看前置" value="in" />
            </el-select>
            <el-button size="small" :loading="neighborLoading" @click="queryNeighbors">查询</el-button>
          </div>
          <div class="gq-row">
            <span class="gq-label">找路径</span>
            <el-input
              v-model="pathSource"
              size="small"
              class="gq-input"
              placeholder="起点知识点"
              clearable
              @keyup.enter="queryGraphPath"
            />
            <span class="gq-arrow">→</span>
            <el-input
              v-model="pathTarget"
              size="small"
              class="gq-input"
              placeholder="终点知识点"
              clearable
              @keyup.enter="queryGraphPath"
            />
            <el-button size="small" :loading="pathLoading" @click="queryGraphPath">查询</el-button>
          </div>

          <div v-if="neighborResult" class="gq-result">
            <p class="gq-summary">
              以「{{ neighborResult.node?.name }}」为中心，{{ neighborResult.hops }} 跳内共有
              <b>{{ neighborResult.neighbor_count }}</b> 个知识点。
            </p>
            <div v-for="(items, hop) in neighborResult.groups" :key="hop" class="gq-group">
              <span class="gq-hop">第 {{ hop }} 跳 · {{ items.length }} 个</span>
              <div class="gq-tags">
                <el-tag
                  v-for="item in items"
                  :key="`${item.tag}-${item.hop}-${item.direction}`"
                  size="small"
                  effect="plain"
                  class="gq-tag"
                  @click="openDetail(item.tag)"
                >{{ item.name }} · {{ neighborDirectionLabel(item.direction) }}</el-tag>
              </div>
            </div>
          </div>

          <div v-if="pathResult" class="gq-result">
            <template v-if="pathResult.found">
              <p class="gq-summary">两点之间最短 <b>{{ pathResult.distance }}</b> 步。</p>
              <div class="gq-chain">
                <template v-for="(node, index) in pathResult.nodes" :key="node.tag">
                  <span class="gq-node" @click="openDetail(node.tag)">{{ node.name }}</span>
                  <span v-if="index < pathResult.nodes.length - 1" class="gq-arrow">→</span>
                </template>
              </div>
              <ul class="gq-steps">
                <li v-for="(step, index) in pathResult.steps" :key="index">
                  {{ step.from?.name }} → {{ step.to?.name }}（{{ relationLabel(step.edge?.relation) }}，{{ neighborDirectionLabel(step.direction) }}）
                </li>
              </ul>
            </template>
            <p v-else class="gq-empty">{{ pathResult.message || '没有找到路径' }}</p>
          </div>

          <p v-if="!neighborResult && !pathResult" class="gq-hint">
            这两种查询只读取图谱里的连线，不会改动你的学习数据。
          </p>
        </section>

        <p v-if="graph?.path_needs_apply" class="graph-notice">
          图谱已更新。点「用图谱重排学习路径」后，路线会按新的先修关系重排，已完成的进度会自动迁移，不会丢。
        </p>

        <p v-if="graphNotice" class="graph-notice">{{ graphNotice }}</p>

        <details v-if="graphDiscarded.length" class="discarded-box">
          <summary>已丢弃 {{ graphDiscarded.length }} 条无效关系（点击查看原因）</summary>
          <ul>
            <li v-for="(item, index) in graphDiscarded" :key="`${item.source}-${item.target}-${index}`">
              {{ nodeName(item.source) }} → {{ nodeName(item.target) }}：{{ item.reason }}
            </li>
          </ul>
        </details>

        <div class="graph-scroll">
          <div ref="graphEl" class="graph-canvas"></div>
        </div>
      </section>

      <section v-if="viewMode === 'knowledge'" class="knowledge-card">
        <header class="card-head">
          <div>
            <h2>知识点路线 <small class="graph-scope">{{ knowledgeStats.total || 44 }} 个知识点全部在路线里</small></h2>
            <p>这条路线的每一站是一个知识点，项目只是练手资源。已掌握的知识点标绿；被前置挡住的会直接告诉你先补哪个。</p>
          </div>
          <el-radio-group v-model="knowledgeFilter" size="small">
            <el-radio-button value="all">全部</el-radio-button>
            <el-radio-button value="remaining">还没掌握</el-radio-button>
            <el-radio-button value="mastered">已掌握</el-radio-button>
          </el-radio-group>
        </header>

        <article v-if="knowledgeCurrent" class="knowledge-next">
          <div class="knowledge-next-copy">
            <small>下一步该补</small>
            <h3>{{ knowledgeCurrent.name }}</h3>
            <p>{{ knowledgeCurrent.reason }}</p>
            <p v-if="knowledgeCurrent.blockers?.length" class="knowledge-next-blockers">
              先补：{{ knowledgeCurrent.blockers.join('、') }}
            </p>
          </div>
          <div class="knowledge-next-actions">
            <el-button size="small" @click="goKnowledgeDoc(knowledgeCurrent)">看教程</el-button>
            <el-button v-if="knowledgeCurrent.project" size="small" type="primary" @click="goKnowledgeLab(knowledgeCurrent)">做实验</el-button>
            <el-button size="small" @click="openKnowledgeQuiz(knowledgeCurrent)">测一测</el-button>
          </div>
        </article>

        <section class="summary-grid knowledge-summary">
          <article class="summary-card">
            <small>已掌握</small>
            <b>{{ knowledgeStats.mastered || 0 }} / {{ knowledgeStats.total || 0 }}</b>
            <span>掌握度达到 70% 的知识点</span>
          </article>
          <article class="summary-card">
            <small>项目配套知识点</small>
            <b>{{ knowledgeStats.project_units || 0 }}</b>
            <span>有编程实验可以练</span>
          </article>
          <article class="summary-card">
            <small>拓展知识点</small>
            <b>{{ knowledgeStats.extension_units || 0 }}</b>
            <span>看教程 + 小测就能推进</span>
          </article>
          <article class="summary-card">
            <small>当前被前置挡住</small>
            <b>{{ knowledgeBlockedCount }}</b>
            <span>先补前面的知识点就能解锁</span>
          </article>
        </section>

        <ul class="knowledge-list">
          <li
            v-for="unit in filteredKnowledgeUnits"
            :key="unit.tag"
            :class="['knowledge-row', `is-${unit.status}`]"
          >
            <span class="knowledge-order">{{ unit.order }}</span>
            <span class="knowledge-main">
              <b>{{ unit.name }}</b>
              <small>
                <em class="mini-tag">{{ unit.module || '课程' }}</em>
                <em :class="['mini-tag', unit.in_course ? 'course' : 'extension']">{{ unit.in_course ? '项目配套' : '拓展' }}</em>
                <em v-if="unit.is_target" class="mini-tag target">目标</em>
                <em v-if="unit.error_focus" class="mini-tag error">常错</em>
                <em v-if="unit.needs_check" class="mini-tag check">建议先测</em>
                <em v-if="unit.difficulty_label" class="mini-tag attr">难度 {{ unit.difficulty_label }}</em>
                <em v-if="unit.cognitive_level" class="mini-tag attr">{{ unit.cognitive_level }}</em>
                <em v-if="unit.study_minutes" class="mini-tag attr">约 {{ formatMinutes(unit.study_minutes) }}</em>
                <em v-if="unit.exam_weight" class="mini-tag attr">考纲 {{ formatWeight(unit.exam_weight) }}</em>
                <em v-if="unit.blockers?.length" class="station-blockers">先补：{{ unit.blockers.join('、') }}</em>
                <em v-else-if="unit.project">可练：{{ unit.project.topic }}</em>
              </small>
            </span>
            <el-tag :color="BAND[unit.mastery_band].color" effect="dark" size="small" class="band-tag">
              {{ BAND[unit.mastery_band].label }}{{ unit.mastery !== null ? ' ' + Math.round(unit.mastery * 100) + '%' : '' }}
            </el-tag>
            <span :class="['station-status', `is-${unit.status}`]">{{ knowledgeStatusLabel(unit) }}</span>
            <span class="station-actions">
              <el-button size="small" text @click="goKnowledgeDoc(unit)">教程</el-button>
              <el-button v-if="unit.project" size="small" text type="primary" @click="goKnowledgeLab(unit)">实验</el-button>
              <el-button size="small" text @click="openKnowledgeQuiz(unit)">测一测</el-button>
            </span>
          </li>
        </ul>
        <p v-if="!filteredKnowledgeUnits.length" class="knowledge-empty">这个筛选下还没有知识点。</p>
      </section>
    </template>

    <el-drawer v-model="detailVisible" :title="detailNode?.name || '知识点'" size="440px">
      <div v-if="detailNode" class="node-detail">
        <div class="detail-head">
          <el-tag :color="BAND[detailNode.mastery_band]?.color" effect="dark" size="small" class="band-tag">
            {{ BAND[detailNode.mastery_band]?.label }}{{ detailMastery }}
          </el-tag>
          <code>{{ detailNode.tag }}</code>
          <el-tag v-if="detailNode.is_current" size="small" type="warning" effect="light">当前站</el-tag>
          <el-tag v-else-if="detailNode.is_done" size="small" type="success" effect="light">已完成</el-tag>
          <el-tag v-else-if="detailNode.personal_state_label" size="small" effect="plain">{{ detailNode.personal_state_label }}</el-tag>
          <el-tag v-else-if="!detailNode.on_path" size="small" type="info" effect="plain">不在当前路线</el-tag>
          <el-tag v-if="detailNode.module" size="small" type="info" effect="plain">{{ detailNode.module }}</el-tag>
        </div>
        <p v-if="detailNode.definition" class="detail-def">{{ detailNode.definition }}</p>

        <div class="detail-block">
          <b>知识点属性</b>
          <div class="meta-grid">
            <span>难度：<b>{{ detailNode.difficulty_label || detailNode.difficulty || '—' }}</b></span>
            <span>认知层次：<b>{{ detailNode.cognitive_level || '—' }}</b></span>
            <span>建议学时：<b>{{ detailNode.study_minutes ? detailNode.study_minutes + ' 分钟' : '—' }}</b></span>
            <span>考纲权重：<b>{{ detailExamWeight }}</b></span>
          </div>
          <div v-if="detailNode.misconceptions?.length" class="meta-sub">
            <b>常见误区</b>
            <ul><li v-for="item in detailNode.misconceptions" :key="item">{{ item }}</li></ul>
          </div>
          <div v-if="detailNode.taught_by?.length" class="meta-sub">
            <b>对应教程</b>
            <ul>
              <li v-for="item in detailNode.taught_by" :key="`${item.type}-${item.ref}`">{{ item.name }}</li>
            </ul>
          </div>
          <div v-if="detailAssessed.length" class="meta-sub">
            <b>测评与实训</b>
            <ul>
              <li v-for="item in detailAssessed" :key="`${item.type}-${item.ref}-${item.name}`">
                {{ item.type === 'lab' ? '实验' : '测评' }}：{{ item.name }}
              </li>
            </ul>
          </div>
        </div>

        <div class="detail-block">
          <b>你的掌握情况</b>
          <div class="mastery-line">
            <span>自身掌握度：<b>{{ detailOwnMastery }}</b></span>
            <el-tag v-if="detailNode.undiagnosed" size="small" type="info" effect="plain">还没有练习证据</el-tag>
            <el-tag v-if="detailNode.weak_self" size="small" type="warning" effect="plain">自身需补强</el-tag>
          </div>
          <p v-if="detailNode.undiagnosed" class="detail-hint">
            还没有做过这个知识点的练习，图谱暂按中性水平估计，练习后会自动校正。
          </p>
          <p v-if="detailEvidenceText" class="detail-evidence">
            <el-tag :type="detailEvidenceType" size="small" effect="plain">
              {{ detailNode.mastery_confidence_label }}
            </el-tag>
            <span>{{ detailEvidenceText }}</span>
          </p>
          <p class="detail-hint">分数由平时小测和代码实验共同计算；证据越多越可信，只做一两题时会向 50% 靠拢。</p>
        </div>

        <div class="detail-block">
          <b>补一次练习证据</b>
          <p class="detail-hint">做 1 道这个知识点的题，答完立即更新掌握度；只有真正答过题，图谱才不会再按「还没练习」估计。</p>
          <el-button size="small" type="primary" plain :loading="quizLoading" @click="openNodeQuiz(detailNode.tag)">
            测一测这个知识点
          </el-button>
        </div>

        <div v-if="detailReadiness" class="detail-block readiness-block">
          <b>就绪度（图谱判断能不能开始学）</b>
          <div class="readiness-row">
            <el-tag :type="detailReadiness.type" size="small" effect="light">{{ detailReadiness.label }}</el-tag>
            <span v-if="detailNode.graph_readiness_score !== null && detailNode.graph_readiness_score !== undefined" class="readiness-score">
              前置就绪度 {{ Math.round(detailNode.graph_readiness_score * 100) }}%
            </span>
          </div>
          <p v-if="detailNode.graph_blockers?.length" class="readiness-blockers">
            还差：{{ detailNode.graph_blockers.join('、') }}。这些前置没打牢时，即使这个知识点分数高，路线也不会让你快进。
          </p>
          <p v-else-if="detailNode.graph_readiness === 'learning'" class="readiness-blockers warn">
            前置知识点还在学习中。建议先巩固前置，再进入这一站，避免越学越吃力。
          </p>
          <p v-else class="readiness-blockers ok">前置都跟得上，可以直接学。</p>
        </div>

        <div v-if="detailNode.key_points?.length" class="detail-block">
          <b>关键要点</b>
          <ul><li v-for="point in detailNode.key_points" :key="point">{{ point }}</li></ul>
        </div>

        <div v-if="detailNode.confusable?.length" class="detail-block">
          <b>容易混淆</b>
          <div class="chip-row">
            <button v-for="tag in detailNode.confusable" :key="tag" class="chip" @click="openDetail(tag)">
              {{ nodeName(tag) }}
            </button>
          </div>
        </div>

        <div v-if="detailNode.parents?.length" class="detail-block">
          <b>直接前置（就绪度按这些算）</b>
          <ul class="parent-list">
            <li v-for="parent in detailNode.parents" :key="parent.tag">
              <div class="parent-head">
                <button class="rel-link" @click="openDetail(parent.tag)">{{ parent.name }}</button>
                <span :class="['rel-origin', parent.origin]">{{ parent.origin === 'expert' ? '专家' : 'AI' }}</span>
                <span v-if="parent.confidence !== null && parent.confidence !== undefined" class="rel-confidence">
                  置信 {{ Math.round(Number(parent.confidence) * 100) }}%
                </span>
              </div>
              <span class="parent-meta">
                掌握 {{ parent.mastery === null || parent.mastery === undefined ? '暂无' : Math.round(parent.mastery * 100) + '%' }}
                · 权重 {{ parent.weight }}
                · {{ parentStateLabel(parent.state) }}
              </span>
              <small v-if="parent.undiagnosed" class="parent-warn">这个前置还没有练习证据，按中性值参与判断</small>
              <small v-if="parent.evidence" class="parent-evidence">依据：{{ parent.evidence }}</small>
            </li>
          </ul>
        </div>

        <div v-if="detailNode.projects?.length" class="detail-block">
          <b>对应实训项目（{{ detailNode.projects.length }} 个）</b>
          <ul class="project-list">
            <li v-for="project in detailNode.projects" :key="`${project.phase_name}-${project.topic}`">
              <div class="project-head">
                <span class="project-topic">{{ project.topic }}</span>
                <el-button
                  v-if="project.module_id && project.lab_id"
                  size="small"
                  text
                  type="primary"
                  @click="goProject(project)"
                >去做实验</el-button>
              </div>
              <small>{{ project.phase_name }} · {{ project.duration || '按需完成' }}</small>
            </li>
          </ul>
        </div>

        <div v-for="group in detailRelations" :key="group.key" class="detail-block">
          <b>{{ group.title }}</b>
          <ul v-if="group.items.length" class="rel-list">
            <li v-for="item in group.items" :key="`${item.source}-${item.target}-${item.relation}`">
              <button class="rel-link" @click="openDetail(item.tag)">{{ item.name }}</button>
              <span v-if="group.key === 'part-of'" class="rel-contain">{{ item.contain_role === 'child' ? '包含' : '属于' }}</span>
              <span :class="['rel-origin', item.origin]">{{ item.origin === 'expert' ? '专家' : 'AI' }}</span>
              <span v-if="item.confidence !== null && item.confidence !== undefined && item.origin !== 'expert'" class="rel-confidence">
                置信 {{ Math.round(Number(item.confidence) * 100) }}%
              </span>
              <span v-if="item.origin !== 'expert' && item.review_status" :class="['rel-review', item.review_status]">
                {{ REVIEW_LABEL[item.review_status] || item.review_status }}
              </span>
              <small v-if="item.reason">{{ item.reason }}</small>
              <small v-if="item.evidence" class="rel-evidence">依据：{{ item.evidence }}</small>
              <span v-if="item.review_status === 'pending' && item.relation !== 'similar'" class="rel-actions">
                <el-button
                  size="small"
                  text
                  type="success"
                  :loading="reviewingEdge === item.key"
                  @click="reviewEdge(item, 'accept')"
                >采纳这条先修</el-button>
                <el-button size="small" text type="danger" @click="reviewEdge(item, 'reject')">拒绝</el-button>
              </span>
            </li>
          </ul>
          <p v-else class="rel-empty">暂无</p>
        </div>
      </div>
    </el-drawer>

    <el-drawer v-model="evalVisible" title="知识图谱测评" size="640px">
      <div v-loading="evalLoading" class="eval-body">
        <template v-if="evaluation">
          <div class="eval-hero">
            <div class="eval-score" :class="evalGradeClass">
              <b>{{ Math.round(evaluation.summary.score) }}</b>
              <span>分</span>
              <em>{{ evaluation.summary.grade }}</em>
            </div>
            <div class="eval-headline">
              <p>{{ evaluation.summary.headline }}</p>
              <div class="eval-meta">
                <el-tag size="small" effect="plain">{{ evaluation.has_graph ? 'AI 图谱' : '专家骨架' }}</el-tag>
                <span>{{ evaluation.node_count }} 个知识点 · {{ evaluation.structure.prerequisite }} 条先修关系</span>
                <span>图谱版本 {{ evaluation.graph_version }}</span>
              </div>
            </div>
          </div>

          <div class="eval-dims">
            <div v-for="dim in evaluation.summary.dimensions" :key="dim.key" class="eval-dim">
              <span>{{ dim.label }}</span>
              <b v-if="dim.score !== null">{{ Math.round(dim.score) }}</b>
              <b v-else class="na">—</b>
              <em>{{ dim.score !== null ? `占 ${dim.weight} 分` : '暂无法评估' }}</em>
            </div>
          </div>

          <div class="eval-block">
            <h4>检查项</h4>
            <ul class="check-list">
              <li v-for="item in evaluation.summary.checks" :key="item.key" :class="item.status">
                <i>{{ item.status === 'pass' ? '✓' : item.status === 'warn' ? '!' : '✕' }}</i>
                <div>
                  <b>{{ item.label }}</b>
                  <span class="check-value">{{ item.value }}</span>
                  <p>{{ item.detail }}</p>
                </div>
              </li>
            </ul>
          </div>

          <div class="eval-block">
            <h4>结构调整</h4>
            <p class="eval-detail">
              {{ evaluation.structure.nodes }} 个知识点、{{ evaluation.structure.edges }} 条关系；
              孤立知识点 {{ evaluation.structure.isolated_nodes.length }} 个，
              悬挂边 {{ evaluation.structure.dangling_edges.length }} 条，
              自环 {{ evaluation.structure.self_loops.length }} 处，
              重复边 {{ evaluation.structure.duplicate_edges.length }} 条，
              环 {{ evaluation.structure.cycles.length }} 个；
              描述覆盖率 {{ Math.round(evaluation.structure.description_coverage * 100) }}%。
            </p>
          </div>

          <div class="eval-block">
            <h4>边质量</h4>
            <p class="eval-detail">{{ evaluation.edge_quality.detail }}</p>
            <ul class="metric-list">
              <li>专家先修边保留率：<b>{{ evalPercent(evaluation.edge_quality.expert_retention) }}</b></li>
              <li>AI 新增关系：<b>{{ evaluation.edge_quality.ai_edges }}</b> 条，其中与专家重复 {{ evaluation.edge_quality.duplicate_of_expert }} 条、方向冲突 {{ evaluation.edge_quality.reversed_conflicts }} 条</li>
              <li>人工审核：采纳 {{ evaluation.edge_quality.review.accepted }} / 拒绝 {{ evaluation.edge_quality.review.rejected }} / 待审 {{ evaluation.edge_quality.review.pending }}</li>
              <li v-if="evaluation.edge_quality.precision !== null">
                精确率 <b>{{ evalPercent(evaluation.edge_quality.precision) }}</b>
                （{{ evalPrecisionLabel(evaluation.edge_quality.precision_source) }}），
                召回率 <b>{{ evalPercent(evaluation.edge_quality.recall) }}</b>
                （{{ evaluation.edge_quality.recall_source === 'expert_retention' ? '专家边保留率' : '金标准正例' }}），
                F1 <b>{{ evalPercent(evaluation.edge_quality.f1) }}</b>
              </li>
            </ul>

            <template v-if="evaluation.edge_quality.gold">
              <p class="eval-subtitle">独立金标准对照</p>
              <ul v-if="evaluation.edge_quality.gold.available" class="metric-list">
                <li>
                  金标准 <b>{{ evaluation.edge_quality.gold.version }}</b>（{{ evaluation.edge_quality.gold.status_label }}）：
                  共 {{ evaluation.edge_quality.gold.labels_total }} 条边，
                  正例 {{ evaluation.edge_quality.gold.positive_total }} 条、负例 {{ evaluation.edge_quality.gold.negative_total }} 条
                </li>
                <li>
                  严格精确率 <b>{{ evalPercent(evaluation.edge_quality.gold.strict_precision) }}</b>（未被金标准覆盖的 AI 边按错误计，是保守下限），
                  判定精确率 <b>{{ evalPercent(evaluation.edge_quality.gold.judged_precision) }}</b>（只算已被标注的 AI 边）
                </li>
                <li>
                  AI 边被金标准判定 {{ evaluation.edge_quality.gold.ai_labeled }} 条（命中正例 {{ evaluation.edge_quality.gold.ai_positive_hits }}、命中负例 {{ evaluation.edge_quality.gold.ai_negative_hits }}），
                  未覆盖 {{ evaluation.edge_quality.gold.ai_unlabeled }} 条；
                  新增正例召回 <b>{{ evalPercent(evaluation.edge_quality.gold.ai_recall_novel) }}</b>
                </li>
                <li>
                  整张图谱覆盖金标准正例 <b>{{ evalPercent(evaluation.edge_quality.gold.graph_coverage) }}</b>
                  （核心 {{ evalPercent(evaluation.edge_quality.gold.graph_core_coverage) }}，
                  补充 {{ evalPercent(evaluation.edge_quality.gold.graph_extended_coverage) }}）
                </li>
                <li>
                  双人标注一致性 kappa：
                  <b>{{ evaluation.edge_quality.gold.kappa === null ? '待补（第二位标注者尚未填写）' : evaluation.edge_quality.gold.kappa }}</b>
                </li>
              </ul>
              <p v-else class="eval-note">{{ evaluation.edge_quality.gold.detail }}</p>
            </template>

            <template v-if="evaluation.edge_quality.stability">
              <p class="eval-subtitle">多次生成稳定性</p>
              <ul v-if="evaluation.edge_quality.stability.status === 'sampled'" class="metric-list">
                <li>
                  已抽检 <b>{{ evaluation.edge_quality.stability.runs }}</b> 次生成，
                  两两 Jaccard 相似度均值 <b>{{ evalPercent(evaluation.edge_quality.stability.mean_jaccard) }}</b>
                  （最低 {{ evalPercent(evaluation.edge_quality.stability.min_jaccard) }}，
                  最高 {{ evalPercent(evaluation.edge_quality.stability.max_jaccard) }}）
                </li>
              </ul>
              <p v-else class="eval-note">{{ evaluation.edge_quality.stability.detail }}</p>
            </template>

            <p class="eval-note">{{ evaluation.edge_quality.method_note }}</p>
          </div>

          <div class="eval-block">
            <h4>路径影响（模拟 3 类学生）</h4>
            <p class="eval-detail">{{ evaluation.path_impact.detail }}</p>
            <el-table :data="evaluation.path_impact.profiles" size="small" class="eval-table">
              <el-table-column prop="name" label="学生类型" width="92" />
              <el-table-column label="拦截快进" width="88">
                <template #default="{ row }">{{ row.with_graph.blocked }}</template>
              </el-table-column>
              <el-table-column label="补先修" width="80">
                <template #default="{ row }">{{ row.with_graph.remedial_focus }}</template>
              </el-table-column>
              <el-table-column label="顺序变化" width="80">
                <template #default="{ row }">{{ row.changed_positions }}</template>
              </el-table-column>
              <el-table-column label="顺序一致性 τ" width="110">
                <template #default="{ row }">{{ row.kendall_tau.toFixed(2) }}</template>
              </el-table-column>
              <el-table-column label="可快进项目" width="96">
                <template #default="{ row }">{{ row.with_graph.skippable }}</template>
              </el-table-column>
            </el-table>
          </div>

          <div v-if="evaluation.path_impact.knowledge_metrics" class="eval-block">
            <h4>路径质量指标（按真实知识点路线计算）</h4>
            <p class="eval-detail">
              下表不是模拟打分，而是把三类学生画像交给真实知识点规划器后，
              从生成的知识点路线里算出来的先修违规率、目标覆盖、难度平滑度与时长贴合度。
            </p>
            <el-table
              :data="evaluation.path_impact.knowledge_metrics.by_profile"
              size="small"
              class="eval-table"
            >
              <el-table-column prop="name" label="学生类型" width="92" />
              <el-table-column label="先修违规率" width="92">
                <template #default="{ row }">{{ evalPercent(row.full.prerequisite_violation_rate) }}</template>
              </el-table-column>
              <el-table-column label="目标覆盖" width="112">
                <template #default="{ row }">
                  {{ row.full.target_covered }}/{{ row.full.target_total }}（{{ evalPercent(row.full.target_coverage) }}）
                </template>
              </el-table-column>
              <el-table-column label="难度平滑度" width="92">
                <template #default="{ row }">{{ evalPercent(row.full.difficulty_smoothness) }}</template>
              </el-table-column>
              <el-table-column label="时长贴合度" width="92">
                <template #default="{ row }">{{ evalPercent(row.full.time_fit) }}</template>
              </el-table-column>
              <el-table-column label="对照：不用图谱违规率" width="136">
                <template #default="{ row }">{{ evalPercent(row.baseline.prerequisite_violation_rate) }}</template>
              </el-table-column>
            </el-table>
            <p class="eval-detail">
              三类学生路线平均差异度：
              <b>{{ evalPercent(evaluation.path_impact.knowledge_metrics.divergence.average_difference) }}</b>。
              数值越高，说明不同基础的学生拿到的学习顺序越不一样。
            </p>
            <p class="eval-note">{{ evaluation.path_impact.knowledge_metrics.method_note }}</p>
          </div>

          <div class="eval-block">
            <h4>证据覆盖（每个知识点有没有测、有没有题）</h4>
            <p class="eval-detail">{{ evaluation.coverage.detail }}</p>
            <el-table :data="evaluation.coverage.per_node" size="small" class="eval-table" max-height="260">
              <el-table-column prop="name" label="知识点" min-width="170" show-overflow-tooltip />
              <el-table-column prop="projects" label="项目" width="60" />
              <el-table-column prop="quiz_questions" label="测评题" width="70" />
              <el-table-column prop="tutorial_docs" label="教程" width="60" />
              <el-table-column label="AI 描述" width="78">
                <template #default="{ row }">{{ row.has_description ? '有' : '无' }}</template>
              </el-table-column>
              <el-table-column prop="similar_count" label="相似边" width="70" />
            </el-table>
          </div>

          <div v-if="evaluation.recommendations?.length" class="eval-block">
            <h4>改进建议</h4>
            <ul class="recommend-list">
              <li v-for="(item, index) in evaluation.recommendations" :key="index">{{ item }}</li>
            </ul>
          </div>

          <div class="eval-actions">
            <el-button size="small" @click="exportEvaluationJson">导出测评数据（JSON）</el-button>
            <el-button size="small" type="primary" @click="printEvaluation">打印 / 存为 PDF</el-button>
            <span class="eval-note">测评时间：{{ formatEvalTime(evaluation.generated_at) }}</span>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-drawer v-model="versionVisible" title="图谱版本历史" size="480px">
      <div v-loading="versionLoading" class="version-body">
        <p class="version-tip">
          每次 AI 生成、人工审核、回滚都会自动留一份快照，最多保留最近 30 份。回滚只改图谱内容，不会删掉你的学习记录。
        </p>
        <ul v-if="versionData?.versions?.length" class="version-list">
          <li
            v-for="item in versionData.versions"
            :key="item.id"
            :class="['version-item', { current: item.is_current }]"
          >
            <div class="version-head">
              <b>V{{ item.version }}</b>
              <el-tag size="small" effect="plain">{{ item.change_type_label }}</el-tag>
              <el-tag v-if="item.is_current" size="small" type="success" effect="plain">当前版本</el-tag>
            </div>
            <p class="version-note">{{ item.change_note || '没有备注' }}</p>
            <p class="version-meta">
              {{ item.node_count }} 个知识点 · {{ item.edge_count }} 条关系 · {{ formatHistoryTime(item.created_at) }}
            </p>
            <el-button
              v-if="!item.is_current"
              size="small"
              type="warning"
              plain
              :loading="restoringVersionId === item.id"
              @click="restoreVersion(item)"
            >回滚到这一版</el-button>
          </li>
        </ul>
        <p v-else-if="!versionLoading" class="version-empty">
          还没有版本快照。生成一次知识图谱后就会自动留底。
        </p>
      </div>
    </el-drawer>
  </div>
</template>

<script setup>
import { computed, nextTick, onBeforeUnmount, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import * as echarts from 'echarts'
import PageHero from '../components/PageHero.vue'
import {
  applyKnowledgeGraphToPath,
  deleteLearningPath,
  generateKnowledgeGraph,
  generateLearningPath,
  getGraphNeighbors,
  getGraphPath,
  getGraphVersions,
  getKnowledgeGraph,
  getKnowledgeGraphEvaluation,
  getLearningRoadmap,
  restoreGraphVersion,
  reviewKnowledgeGraphEdge,
  startQuickQuiz,
  submitQuickQuiz as submitQuickQuizApi,
} from '../api/learning'

const router = useRouter()

const VIEWS = [
  { key: 'roadmap', label: '学习路线图' },
  { key: 'knowledge', label: '知识点路线' },
  { key: 'graph', label: '知识图谱' },
]

const BAND = {
  high: { label: '可快进', color: '#2f9e6b', desc: '掌握度 ≥ 70%' },
  medium: { label: '在学', color: '#4c7ff0', desc: '掌握度 40%–70%' },
  low: { label: '需补强', color: '#e08a3c', desc: '掌握度 < 40%' },
  unknown: { label: '暂无诊断', color: '#9aa4b6', desc: '还没有练习证据' },
}
const STATUS = {
  done: { label: '已完成', border: '#2f9e6b' },
  current: { label: '当前站', border: '#ff6b4a' },
  locked: { label: '前置未完成', border: '#c9d0dd' },
  todo: { label: '待学习', border: '#c9d0dd' },
}

const loading = ref(false)
const generating = ref(false)
const regenerating = ref(false)
const hasPath = ref(false)
const quizVisible = ref(false)
const quizLoading = ref(false)
const quizSubmitting = ref(false)
const quizSessionId = ref(null)
const quizQuestions = ref([])
const quizAnswers = reactive({})
const quizMultiAnswers = reactive({})
const quizMode = ref('placement')
const quizFocusTag = ref('')
const quizTitle = computed(() => (
  quizMode.value === 'diagnose'
    ? `测一测：${nodeName(quizFocusTag.value) || '知识点'}`
    : '5 道题，快速判断你的起点'
))
const quizHint = computed(() => (
  quizMode.value === 'diagnose'
    ? '这道题用来给这个知识点补一条练习证据，提交后掌握度会立刻更新。'
    : '答完会按你的掌握情况调整路线起点、项目顺序和学时。不会的题可以留空，不影响生成。'
))
const roadmap = ref(null)
const availableTracks = ref([])
const mapEl = ref(null)
const viewMode = ref('roadmap')
const graph = ref(null)
const graphLoading = ref(false)
const graphGenerating = ref(false)
const graphApplying = ref(false)
const graphEl = ref(null)
const graphScope = ref('mine')
const evalVisible = ref(false)
const evalLoading = ref(false)
const evaluation = ref(null)
const detailVisible = ref(false)
const detailTag = ref('')
const edgeFilter = ref('all')
const reviewingEdge = ref('')
// 图查询（N 跳邻居 / 两点路径）
const neighborRef = ref('')
const neighborHops = ref(1)
const neighborDirection = ref('both')
const neighborResult = ref(null)
const neighborLoading = ref(false)
const pathSource = ref('')
const pathTarget = ref('')
const pathResult = ref(null)
const pathLoading = ref(false)
// 版本历史
const versionVisible = ref(false)
const versionLoading = ref(false)
const versionData = ref(null)
const restoringVersionId = ref(null)
let chart = null
let graphChart = null
let resizeObserver = null

const summary = computed(() => roadmap.value?.summary || {})
const learningDepth = computed(() => roadmap.value?.learning_depth || '')
const reviewNotice = computed(() => roadmap.value?.review_notice || null)
const stations = computed(() => roadmap.value?.stations || [])
const lowMasteryCount = computed(() => stations.value.filter(s => s.mastery_band === 'low').length)
const highMasteryCount = computed(() => stations.value.filter(s => s.mastery_band === 'high').length)

// ---------- 目标与预算 / 学习者画像（#43）----------
const PREFERENCE_STORE_KEY = 'learning_path_preferences'
const EMPTY_PREFERENCES = { target_tags: [], weekly_hours: null, deadline_weeks: null, preferred_mode: '' }
const preferenceVisible = ref(false)
const preferenceForm = reactive({ ...EMPTY_PREFERENCES })
const learnerProfile = computed(() => roadmap.value?.learner_profile || null)
const pathStrategy = computed(() => roadmap.value?.path_strategy || null)
const pathAlternatives = computed(() => roadmap.value?.path_alternatives || [])
const targetOptions = ref([])

async function ensureTargetOptions() {
  if (targetOptions.value.length) return
  if (knowledgeUnits.value.length) {
    targetOptions.value = knowledgeUnits.value.map(unit => ({ tag: unit.tag, name: unit.name }))
    return
  }
  try {
    const data = await getKnowledgeGraph('full')
    targetOptions.value = (data?.nodes || []).map(node => ({ tag: node.tag, name: node.name }))
  } catch {
    targetOptions.value = []
  }
}

function loadStoredPreferences() {
  try {
    const raw = localStorage.getItem(PREFERENCE_STORE_KEY)
    if (!raw) return { ...EMPTY_PREFERENCES, target_tags: [] }
    const data = JSON.parse(raw)
    return {
      target_tags: Array.isArray(data.target_tags) ? data.target_tags : [],
      weekly_hours: Number(data.weekly_hours) || null,
      deadline_weeks: Number(data.deadline_weeks) || null,
      preferred_mode: data.preferred_mode || '',
    }
  } catch {
    return { ...EMPTY_PREFERENCES, target_tags: [] }
  }
}

function openPreferenceDialog() {
  ensureTargetOptions()
  const stored = loadStoredPreferences()
  const budget = learnerProfile.value?.time_budget || {}
  const preferences = learnerProfile.value?.preferences || {}
  preferenceForm.target_tags = (learnerProfile.value?.target_names?.length
    ? (learnerProfile.value.target_tags || [])
    : stored.target_tags).slice()
  preferenceForm.weekly_hours = budget.weekly_hours ?? stored.weekly_hours
  preferenceForm.deadline_weeks = budget.deadline_weeks ?? stored.deadline_weeks
  preferenceForm.preferred_mode = preferences.mode || stored.preferred_mode || ''
  preferenceVisible.value = true
}

async function savePreferences(regenerate = false) {
  const payload = {
    target_tags: preferenceForm.target_tags || [],
    weekly_hours: preferenceForm.weekly_hours || null,
    deadline_weeks: preferenceForm.deadline_weeks || null,
    preferred_mode: preferenceForm.preferred_mode || '',
  }
  localStorage.setItem(PREFERENCE_STORE_KEY, JSON.stringify(payload))
  preferenceVisible.value = false
  if (!regenerate) {
    ElMessage.success('已保存，下次重新生成路线时生效')
    return
  }
  await generatePath()
}

async function useAlternative(alternative) {
  if (!alternative?.mode || !alternative?.strategy) return
  if (pathStrategy.value?.strategy === alternative.strategy) {
    ElMessage.info('当前已经在这条方案上')
    return
  }
  const payload = { ...loadStoredPreferences(), preferred_mode: alternative.mode }
  localStorage.setItem(PREFERENCE_STORE_KEY, JSON.stringify(payload))
  await generatePath()
}


// ---------- 路线变更记录（#45） ----------
const pathHistory = computed(() => roadmap.value?.path_history || [])

function historyMasteryChanges(item) {
  return (item?.reason?.mastery_changes || []).slice(0, 6)
}

function formatMasteryChange(change) {
  const before = change?.before === null || change?.before === undefined
    ? '无记录'
    : `${Math.round(change.before * 100)}%`
  const after = change?.after === null || change?.after === undefined
    ? '—'
    : `${Math.round(change.after * 100)}%`
  return `：${before} → ${after}`
}

function historyDiffTags(item) {
  const counts = item?.counts || {}
  const tags = []
  if (counts.skippable_added) tags.push(`${counts.skippable_added} 个任务变为可快进`)
  if (counts.skippable_removed) tags.push(`${counts.skippable_removed} 个任务取消快进`)
  if (counts.moved) tags.push(`${counts.moved} 个任务调整先后`)
  if (counts.duration_changed) tags.push(`${counts.duration_changed} 个任务改时长`)
  if (counts.added) tags.push(`新增 ${counts.added} 个补先修任务`)
  if (counts.removed) tags.push(`移除 ${counts.removed} 个任务`)
  if (counts.gated_added) tags.push(`${counts.gated_added} 个任务被前置锁定`)
  if (counts.gated_removed) tags.push(`${counts.gated_removed} 个任务解除锁定`)
  return tags
}

function formatHistoryTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

const phaseGroups = computed(() => {
  const groups = (roadmap.value?.phases || []).map(phase => ({ ...phase, stations: [] }))
  stations.value.forEach(station => {
    if (groups[station.phase_index]) groups[station.phase_index].stations.push(station)
  })
  return groups
})

// ---------- 知识点路线（路径最小单位 = 知识点） ----------
const knowledgeFilter = ref('all')
const knowledgePath = computed(() => roadmap.value?.knowledge_path || null)
const knowledgeStats = computed(() => knowledgePath.value || {})
const knowledgeUnits = computed(() => knowledgePath.value?.units || [])
const knowledgeCurrent = computed(() => knowledgePath.value?.current || null)
const knowledgeBlockedCount = computed(() => knowledgeUnits.value.filter(unit => unit.status === 'locked').length)
const filteredKnowledgeUnits = computed(() => {
  if (knowledgeFilter.value === 'remaining') return knowledgeUnits.value.filter(unit => unit.status !== 'done')
  if (knowledgeFilter.value === 'mastered') return knowledgeUnits.value.filter(unit => unit.status === 'done')
  return knowledgeUnits.value
})
const KNOWLEDGE_STATUS = {
  done: '已掌握',
  current: '下一步',
  locked: '前置未学',
  todo: '待安排',
}
function knowledgeStatusLabel(unit) {
  return KNOWLEDGE_STATUS[unit?.status] || ''
}
function formatMinutes(minutes) {
  const value = Number(minutes) || 0
  if (value >= 60) {
    const hours = value / 60
    return `${Number.isInteger(hours) ? hours : hours.toFixed(1)} 小时`
  }
  return `${value} 分钟`
}
function formatWeight(weight) {
  const value = Number(weight)
  return Number.isFinite(value) && value > 0 ? `${(value * 100).toFixed(1)}%` : '—'
}

/** 分层布局：x = 拓扑深度，y = 同层站点的等距分布 */
const layout = computed(() => {
  const tiers = new Map()
  stations.value.forEach(station => {
    const tier = station.tier || 0
    if (!tiers.has(tier)) tiers.set(tier, [])
    tiers.get(tier).push(station)
  })
  const keys = [...tiers.keys()].sort((a, b) => a - b)
  const rows = Math.max(...keys.map(key => tiers.get(key).length), 1)
  const height = Math.max(380, rows * 96 + 96)
  const width = Math.max(760, keys.length * 210 + 180)
  const pos = {}
  keys.forEach((key, tierIndex) => {
    const group = tiers.get(key)?.slice().sort((a, b) => a.day - b.day) || []
    const step = height / (group.length + 1)
    group.forEach((station, index) => {
      pos[station.key] = { x: tierIndex * 210 + 110, y: Math.round(step * (index + 1)) }
    })
  })
  return { pos, height, width }
})

// ---------- 知识图谱（§5.8 第二版） ----------
const graphNodes = computed(() => graph.value?.nodes || [])
const graphEdges = computed(() => graph.value?.edges || [])
const graphStats = computed(() => graph.value?.stats || {})
const graphView = computed(() => graph.value?.view || {})
const graphNotice = computed(() => graph.value?.notice || '')
const graphDiscarded = computed(() => graph.value?.discarded_edges || [])

const REVIEW_LABEL = {
  accepted: 'AI 已采纳',
  pending: '待审核',
  rejected: '已拒绝',
}

/** 边分类：专家 / AI 已采纳 / AI 待审核 / AI 已拒绝 / 相似 / 包含 */
function edgeState(edge) {
  if (edge.relation === 'part-of') return 'part-of'
  if (edge.relation === 'similar') return 'similar'
  if (edge.origin === 'expert') return 'expert'
  if (edge.review_status === 'rejected') return 'rejected'
  if (edge.review_status === 'pending') return 'pending'
  if (edge.review_status === 'accepted') return 'accepted'
  // 兼容旧图谱：没有审核字段时按置信度判断
  const confidence = Number(edge.confidence)
  if (!Number.isFinite(confidence)) return 'accepted'
  return confidence >= 0.75 ? 'accepted' : confidence >= 0.5 ? 'pending' : 'rejected'
}

const filteredGraphEdges = computed(() => {
  const edges = graphEdges.value
  if (edgeFilter.value === 'expert') return edges.filter(edge => edge.origin === 'expert')
  if (edgeFilter.value === 'ai') return edges.filter(edge => edge.origin !== 'expert')
  if (edgeFilter.value === 'pending') return edges.filter(edge => edge.review_status === 'pending')
  return edges
})
/** 图谱对路径的实际影响：图谱页取接口 impact，路线图页取 roadmap.graph */
const graphImpact = computed(() => graph.value?.impact || roadmap.value?.graph || {})
const pathSkipBlocked = computed(() => graphImpact.value?.path_operator?.skip_blocked?.length || 0)
/** 路径级反事实：先补哪个知识点最能缩短路线（后端只做推演，不改学习记录） */
const counterfactual = computed(() => roadmap.value?.counterfactual || null)

/** 锁定原因分两种：图谱判定前置薄弱，或只是前一个站点还没做完 */
function statusLabel(station) {
  if (!station) return ''
  if (station.status !== 'locked') return STATUS[station.status]?.label || ''
  return station.graph_readiness === 'blocked' || station.graph_gated ? '图谱锁定' : '前置未完成'
}

const READINESS = {
  ready: { label: '前置已就绪，可以直接学', type: 'success' },
  learning: { label: '前置还在学，建议先巩固', type: 'warning' },
  blocked: { label: '前置薄弱，已被图谱锁定', type: 'danger' },
}

const nodeIndex = computed(() => {
  const map = {}
  graphNodes.value.forEach(node => { map[node.tag] = node })
  return map
})

const detailNode = computed(() => (detailTag.value ? nodeIndex.value[detailTag.value] : null) || null)
const detailMastery = computed(() => {
  const value = detailNode.value?.mastery
  return value === null || value === undefined ? '' : ` ${Math.round(value * 100)}%`
})
const detailOwnMastery = computed(() => {
  const value = detailNode.value?.own_mastery
  return value === null || value === undefined ? '暂无' : `${Math.round(Number(value) * 100)}%`
})
const detailReadiness = computed(() => READINESS[detailNode.value?.graph_readiness] || null)
const detailExamWeight = computed(() => {
  const value = Number(detailNode.value?.exam_weight)
  return Number.isFinite(value) && value > 0 ? `${(value * 100).toFixed(1)}%` : '—'
})
const detailAssessed = computed(() => (detailNode.value?.assessed_by || []).slice(0, 6))
const detailEvidenceText = computed(() => {
  const node = detailNode.value
  if (!node || node.mastery === null || node.mastery === undefined) return ''
  if (node.mastery_confidence === null || node.mastery_confidence === undefined) return ''
  const detail = node.mastery_evidence_detail || {}
  const parts = []
  if (detail.quiz_attempts) parts.push(`测评 ${detail.quiz_attempts} 题（对 ${detail.quiz_correct || 0} 题）`)
  if (detail.lab_attempts) parts.push(`代码实验 ${detail.lab_attempts} 次`)
  return [
    `掌握 ${Math.round(node.mastery * 100)}%`,
    `证据 ${node.mastery_evidence ?? 0} 次`,
    node.mastery_confidence_label || '',
    parts.length ? `来源：${parts.join('、')}` : '',
  ].filter(Boolean).join(' · ')
})
const detailEvidenceType = computed(() => {
  const label = detailNode.value?.mastery_confidence_label
  if (label === '较可信') return 'success'
  if (label === '初步可信') return 'warning'
  return 'info'
})

function nodeName(tag) {
  return nodeIndex.value[tag]?.name || tag || '未知知识点'
}

function parentStateLabel(state) {
  if (state === 'blocked') return '这条链路还有前置没打牢'
  if (state === 'learning') return '在学但还不够稳'
  return '已就绪'
}

/** 二级详情：包含 / 先修（入边）/ 后继（出边）/ 相似 四组关联 */
const detailRelations = computed(() => {
  const node = detailNode.value
  if (!node) return []
  const partOf = [], prereq = [], next = [], similar = []
  graphEdges.value.forEach(edge => {
    const other = edge.source === node.tag ? edge.target : edge.target === node.tag ? edge.source : null
    if (!other) return
    const item = {
      key: `${edge.source}-${edge.target}-${edge.relation}`,
      tag: other,
      name: nodeIndex.value[other]?.name || other,
      reason: edge.reason,
      evidence: edge.evidence,
      origin: edge.origin,
      confidence: edge.confidence,
      review_status: edge.review_status,
      relation: edge.relation,
      source: edge.source,
      target: edge.target,
      contain_role: edge.source === node.tag ? 'child' : 'parent',
    }
    if (edge.relation === 'part-of') partOf.push(item)
    else if (edge.relation === 'similar') similar.push(item)
    else if (edge.target === node.tag) prereq.push(item)
    else next.push(item)
  })
  return [
    { key: 'part-of', title: '包含 / 属于（目录层级，不代表学习先后）', items: partOf },
    { key: 'prereq', title: '先修（学它之前建议先掌握）', items: prereq },
    { key: 'next', title: '后继（掌握它之后可以学）', items: next },
    { key: 'similar', title: '相似（易混淆，适合对比学习）', items: similar },
  ]
})

/** 颜色工具：把十六进制色混入白色（ratio 越大越浅） */
function shade(hex, ratio) {
  const n = parseInt(hex.slice(1), 16)
  const mix = c => Math.round(c + (255 - c) * ratio)
  return `rgb(${mix((n >> 16) & 255)}, ${mix((n >> 8) & 255)}, ${mix(n & 255)})`
}

/** 颜色工具：把十六进制色转成带透明度的 rgba */
function alpha(hex, a) {
  const n = parseInt(hex.slice(1), 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${a})`
}

function edgeLineStyle(edge) {
  const state = edgeState(edge)
  if (state === 'part-of') {
    return { color: '#8a96ad', width: 1.2, type: 'dotted', curveness: 0, opacity: 0.55 }
  }
  if (state === 'similar') {
    return {
      color: '#a97fe6', width: 1.8, type: 'dashed', curveness: 0.24, opacity: 0.9,
      shadowBlur: 6, shadowColor: 'rgba(169,127,230,.35)',
    }
  }
  if (state === 'expert') {
    return { color: '#5d6b82', width: 2, curveness: 0.1, opacity: 0.92 }
  }
  if (state === 'rejected') {
    return { color: '#c9d0dd', width: 1.2, type: 'dashed', curveness: 0.1, opacity: 0.4 }
  }
  if (state === 'pending') {
    return {
      color: '#e08a3c', width: 1.8, type: 'dashed', curveness: 0.12, opacity: 0.95,
      shadowBlur: 6, shadowColor: 'rgba(224,138,60,.28)',
    }
  }
  const confidence = Number(edge.confidence)
  const ratio = Number.isFinite(confidence) ? confidence : 1
  return {
    color: '#2f9e9e', width: 1.6 + ratio * 1.2, curveness: 0.12, opacity: 0.6 + ratio * 0.35,
  }
}

function buildGraphOption() {
  const edgesInView = filteredGraphEdges.value
  const degree = {}
  edgesInView.forEach(edge => {
    degree[edge.source] = (degree[edge.source] || 0) + 1
    degree[edge.target] = (degree[edge.target] || 0) + 1
  })

  const nodes = graphNodes.value.map(node => {
    const band = BAND[node.mastery_band] || BAND.unknown
    const blocked = node.graph_readiness === 'blocked'
    const borderColor = node.is_current
      ? '#ff6b4a'
      : node.is_done
        ? '#2f9e6b'
        : node.personal_state === 'frontier'
          ? '#2f9e9e'
          : blocked
            ? '#e0644a'
            : '#ffffff'
    const borderWidth = node.is_current
      ? 4
      : node.is_done || node.personal_state === 'frontier' || blocked
        ? 3.5
        : 2
    return {
      id: node.tag,
      name: node.name,
      raw: node,
      symbolSize: 34 + Math.min(degree[node.tag] || 0, 8) * 4,
      itemStyle: {
        color: {
          type: 'radial',
          x: 0.36,
          y: 0.3,
          r: 0.78,
          colorStops: [
            { offset: 0, color: shade(band.color, 0.48) },
            { offset: 1, color: band.color },
          ],
        },
        borderColor,
        borderWidth,
        borderType: node.undiagnosed ? 'dashed' : 'solid',
        shadowBlur: node.is_current ? 22 : 16,
        shadowColor: alpha(node.is_current ? '#ff6b4a' : band.color, node.is_current ? 0.5 : 0.38),
      },
      label: {
        show: true,
        position: 'bottom',
        distance: 8,
        fontSize: 11.5,
        fontWeight: 600,
        color: '#33405c',
        textBorderColor: '#ffffff',
        textBorderWidth: 3,
        width: 118,
        overflow: 'break',
        lineHeight: 15,
      },
    }
  })

  const links = edgesInView.map(edge => ({
    source: edge.source,
    target: edge.target,
    raw: edge,
    lineStyle: edgeLineStyle(edge),
  }))

  return {
    animationDuration: 800,
    animationEasingUpdate: 'cubicOut',
    backgroundColor: {
      type: 'radial',
      x: 0.5,
      y: 0.45,
      r: 0.8,
      colorStops: [
        { offset: 0, color: '#fdfdff' },
        { offset: 1, color: '#eef2fa' },
      ],
    },
    tooltip: {
      confine: true,
      backgroundColor: 'rgba(255,255,255,.98)',
      borderColor: '#dfe6f5',
      borderWidth: 1,
      padding: [10, 13],
      textStyle: { color: '#33405c', fontSize: 12, lineHeight: 19 },
      extraCssText: 'border-radius:12px; box-shadow:0 10px 28px rgba(24,38,72,.16);',
      formatter: (params) => {
        if (params.dataType === 'edge') {
          const edge = params.data.raw
          const state = edgeState(edge)
          const relationLabel = edge.relation === 'similar' ? '相似关系' : '先修关系'
          const originLabel = edge.origin === 'expert' ? '课程先修表（专家维护，不可修改）' : 'AI 推断'
          const confidence = edge.confidence === null || edge.confidence === undefined
            ? ''
            : `置信度：${Math.round(Number(edge.confidence) * 100)}%`
          const status = edge.origin === 'expert'
            ? '生效状态：已生效'
            : `审核状态：${REVIEW_LABEL[edge.review_status] || (state === 'accepted' ? '已采纳' : '旧图谱未标注')}`
          return [
            `<b>${nodeName(edge.source)} → ${nodeName(edge.target)}</b>`,
            `${relationLabel} · ${originLabel}`,
            confidence,
            status,
            edge.reason ? `理由：${edge.reason}` : '',
            edge.evidence ? `依据：${edge.evidence}` : '',
          ].filter(Boolean).join('<br/>')
        }
        const node = params.data.raw
        const band = BAND[node.mastery_band] || BAND.unknown
        const mastery = node.mastery === null || node.mastery === undefined ? '暂无' : `${Math.round(node.mastery * 100)}%`
        const ownMastery = node.own_mastery === null || node.own_mastery === undefined
          ? '暂无'
          : `${Math.round(Number(node.own_mastery) * 100)}%`
        const readiness = READINESS[node.graph_readiness]
        const blockedBy = node.graph_blockers?.length ? `还差：${node.graph_blockers.join('、')}` : ''
        const position = node.personal_state_label
          || (node.is_current
            ? '当前站'
            : node.is_done
              ? '已完成'
              : node.on_path
                ? '待学习'
                : '不在当前路线')
        return [
          `<b>${node.name}</b>`,
          node.definition || '',
          node.module ? `所属模块：${node.module}` : '',
          `节点状态：${position}`,
          `自身掌握度：${ownMastery}${node.undiagnosed ? '（还没有练习证据）' : ''}`,
          `路线掌握度：${mastery}（${band.label}）`,
          readiness ? `图谱判断：${readiness.label}` : '',
          blockedBy,
          node.projects?.length ? `对应 ${node.projects.length} 个实训项目` : '',
          '点击查看要点、前置与项目',
        ].filter(Boolean).join('<br/>')
      },
    },
    series: [{
      type: 'graph',
      layout: 'force',
      roam: true,
      draggable: true,
      data: nodes,
      links,
      force: { repulsion: 520, edgeLength: [120, 200], gravity: 0.05, friction: 0.12 },
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 9],
      scaleLimit: { min: 0.6, max: 3 },
      emphasis: {
        focus: 'adjacency',
        scale: 1.12,
        itemStyle: { borderWidth: 3, shadowBlur: 22 },
        lineStyle: { width: 2.8, opacity: 1 },
        label: { fontWeight: 700, color: '#17213a' },
      },
      blur: {
        itemStyle: { opacity: 0.16 },
        lineStyle: { opacity: 0.06 },
        label: { opacity: 0.15 },
      },
      labelLayout: { hideOverlap: true },
    }],
  }
}

function shortTopic(topic) {
  const text = String(topic || '').split('：').pop() || ''
  return text.length > 9 ? `${text.slice(0, 9)}…` : text
}

function buildOption() {
  const nodes = stations.value.map(station => {
    const point = layout.value.pos[station.key] || { x: 110, y: 60 }
    const band = BAND[station.mastery_band] || BAND.unknown
    const status = STATUS[station.status] || STATUS.todo
    return {
      id: station.key,
      name: station.topic,
      x: point.x,
      y: point.y,
      symbol: 'roundRect',
      symbolSize: [148, 54],
      raw: station,
      itemStyle: {
        color: band.color,
        borderColor: status.border,
        borderWidth: station.status === 'current' ? 3 : 1.5,
        opacity: station.status === 'locked' ? 0.55 : 1,
        shadowBlur: station.status === 'current' ? 14 : 0,
        shadowColor: 'rgba(255,107,74,.4)',
      },
      label: {
        show: true,
        position: 'inside',
        formatter: `{d|第${station.day}站}\n{t|${shortTopic(station.topic)}}`,
        rich: {
          d: { fontSize: 10, lineHeight: 15, color: 'rgba(255,255,255,.82)' },
          t: { fontSize: 12, lineHeight: 16, fontWeight: 650, color: '#fff' },
        },
      },
    }
  })

  const edges = (roadmap.value?.edges || []).map(edge => ({
    source: edge.source,
    target: edge.target,
    lineStyle: edge.kind === 'sequence'
      ? { color: '#cfd6e4', width: 1.5, type: 'dashed', curveness: 0.06 }
      : { color: '#a6b1c7', width: 1.5, curveness: 0.08 },
  }))

  return {
    animationDuration: 420,
    tooltip: {
      confine: true,
      formatter: (params) => {
        const station = params.data?.raw
        if (!station) return ''
        const band = BAND[station.mastery_band] || BAND.unknown
        const mastery = station.mastery === null ? '暂无' : `${Math.round(station.mastery * 100)}%`
        const subs = `教程${station.sub_tasks.learn ? '✓' : '·'} 实验${station.sub_tasks.code ? '✓' : '·'} 练习${station.sub_tasks.quiz ? '✓' : '·'}`
        return [
          `<b>第 ${station.day} 天 · ${station.topic}</b>`,
          `${station.phase_name || ''}`,
          `掌握度：${mastery}（${band.label}）`,
          `进度：${subs}`,
          `状态：${statusLabel(station)}`,
        ].join('<br/>')
      },
    },
    series: [{
      type: 'graph',
      layout: 'none',
      roam: true,
      draggable: false,
      data: nodes,
      links: edges,
      edgeSymbol: ['none', 'arrow'],
      edgeSymbolSize: [0, 7],
      lineStyle: { color: '#a6b1c7', width: 1.5 },
      emphasis: { focus: 'adjacency', lineStyle: { width: 2.4 } },
    }],
  }
}

/** 按当前视图渲染对应图表（两个视图互斥挂载，切换后重建实例） */
function renderActive() {
  if (viewMode.value === 'roadmap') {
    if (!mapEl.value) return
    if (!chart) chart = echarts.init(mapEl.value)
    chart.setOption(buildOption(), true)
    return
  }
  if (viewMode.value === 'knowledge') return
  if (!graphEl.value) return
  if (!graphChart) {
    graphChart = echarts.init(graphEl.value)
    graphChart.on('click', params => {
      if (params.dataType === 'node' && params.data?.raw) openDetail(params.data.raw.tag)
    })
  }
  graphChart.setOption(buildGraphOption(), true)
}

function disposeCharts() {
  chart?.dispose()
  chart = null
  graphChart?.dispose()
  graphChart = null
}

function bindResize() {
  resizeObserver?.disconnect()
  if (mapEl.value) resizeObserver?.observe(mapEl.value)
  if (graphEl.value) resizeObserver?.observe(graphEl.value)
}

function openDetail(tag) {
  detailTag.value = tag
  detailVisible.value = true
}

async function switchView(mode) {
  if (viewMode.value === mode) return
  disposeCharts()
  viewMode.value = mode
  if (mode === 'graph' && !graph.value) await loadGraph()
  await nextTick()
  renderActive()
  bindResize()
}

async function loadGraph(scope = graphScope.value) {
  graphLoading.value = true
  try {
    graph.value = (await getKnowledgeGraph(scope)) || null
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取知识图谱失败')
  } finally {
    graphLoading.value = false
  }
}

async function changeGraphScope(scope) {
  await loadGraph(scope)
  await nextTick()
  renderActive()
  bindResize()
}

async function generateGraph() {
  graphGenerating.value = true
  try {
    await generateKnowledgeGraph()
    ElMessage.success('已生成知识图谱')
    await loadGraph(graphScope.value)
    await nextTick()
    renderActive()
    bindResize()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '生成知识图谱失败')
  } finally {
    graphGenerating.value = false
  }
}

async function applyGraphToPath() {
  graphApplying.value = true
  try {
    const result = await applyKnowledgeGraphToPath()
    const migrated = result?.migrated_count || 0
    const remedial = result?.graph?.remedial_inserted || 0
    ElMessage.success(
      `已按知识图谱重排路线：迁移 ${migrated} 条已完成进度${remedial ? `，新增 ${remedial} 个补先修任务` : ''}`,
    )
    if (graph.value) graph.value.path_needs_apply = false
    await load()
    await loadGraph()
    await nextTick()
    renderActive()
    bindResize()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '应用知识图谱失败')
  } finally {
    graphApplying.value = false
  }
}

// ---------- 图查询：N 跳邻居 / 两点路径 ----------
const RELATION_LABELS = { prerequisite: '先修', similar: '相似', 'part-of': '包含' }

function relationLabel(relation) {
  return RELATION_LABELS[relation] || relation || '关系'
}

function neighborDirectionLabel(direction) {
  return direction === 'out' ? '后继' : '前置'
}

async function queryNeighbors() {
  const ref = neighborRef.value.trim()
  if (!ref) {
    ElMessage.warning('先输入一个知识点名称或 tag')
    return
  }
  neighborLoading.value = true
  try {
    neighborResult.value = await getGraphNeighbors({
      ref,
      hops: neighborHops.value,
      direction: neighborDirection.value,
    })
    pathResult.value = null
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '查询邻居失败')
  } finally {
    neighborLoading.value = false
  }
}

async function queryGraphPath() {
  const source = pathSource.value.trim()
  const target = pathTarget.value.trim()
  if (!source || !target) {
    ElMessage.warning('起点和终点都要填')
    return
  }
  pathLoading.value = true
  try {
    pathResult.value = await getGraphPath({ source, target })
    neighborResult.value = null
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '查询路径失败')
  } finally {
    pathLoading.value = false
  }
}

// ---------- 图谱版本历史 ----------
async function openVersions() {
  versionVisible.value = true
  versionLoading.value = true
  try {
    versionData.value = await getGraphVersions({ limit: 30 })
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '读取版本历史失败')
  } finally {
    versionLoading.value = false
  }
}

async function restoreVersion(item) {
  try {
    await ElMessageBox.confirm(
      `回滚到 V${item.version} 后，知识图谱会变回这一版的内容；已完成的练习记录不会丢。回滚本身也会留一份快照，之后还能退回来。`,
      `回滚到 V${item.version}`,
      { confirmButtonText: '确认回滚', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  restoringVersionId.value = item.id
  try {
    const restored = await restoreGraphVersion(item.id, { note: `回滚到 V${item.version}` })
    ElMessage.success(`已回滚到 V${item.version}`)
    if (restored) graph.value = restored
    await load()
    await loadGraph(graphScope.value)
    await nextTick()
    renderActive()
    bindResize()
    await openVersions()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '回滚图谱失败')
  } finally {
    restoringVersionId.value = null
  }
}

// ---------- 知识图谱测评 ----------
const evalGradeClass = computed(() => {
  const score = evaluation.value?.summary?.score ?? 0
  return score >= 85 ? 'excellent' : score >= 70 ? 'good' : score >= 60 ? 'pass' : 'weak'
})

function evalPercent(value) {
  return value === null || value === undefined ? '—' : `${Math.round(value * 100)}%`
}

function evalPrecisionLabel(source) {
  const labels = {
    gold_judged: '金标准判定精确率',
    gold_strict: '金标准严格下限',
    human_review: '人工审核采纳率',
    expert_reference: '与专家边核对',
  }
  return labels[source] || '代理指标'
}

function formatEvalTime(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value
  return date.toLocaleString('zh-CN', { hour12: false })
}

async function openEvaluation() {
  evalVisible.value = true
  evalLoading.value = true
  try {
    evaluation.value = (await getKnowledgeGraphEvaluation()) || null
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '知识图谱测评失败')
  } finally {
    evalLoading.value = false
  }
}

function exportEvaluationJson() {
  if (!evaluation.value) return
  const blob = new Blob([JSON.stringify(evaluation.value, null, 2)], { type: 'application/json;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  const stamp = new Date().toISOString().slice(0, 10)
  link.href = url
  link.download = `knowledge-graph-evaluation-${stamp}.json`
  link.click()
  URL.revokeObjectURL(url)
}

function printEvaluation() {
  const report = evaluation.value
  if (!report) return
  const esc = (text) => String(text ?? '').replace(/[&<>]/g, (ch) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[ch]))
  const dims = report.summary.dimensions
    .map((dim) => `<td><b>${dim.score === null ? '—' : Math.round(dim.score)}</b><small>${dim.label}</small></td>`)
    .join('')
  const checks = report.summary.checks
    .map((item) => `<tr><td>${item.status === 'pass' ? '通过' : item.status === 'warn' ? '提示' : '不通过'}</td><td>${esc(item.label)}</td><td>${esc(item.value)}</td><td>${esc(item.detail)}</td></tr>`)
    .join('')
  const profiles = report.path_impact.profiles
    .map((row) => `<tr><td>${esc(row.name)}</td><td>${row.with_graph.blocked}</td><td>${row.with_graph.remedial_focus}</td><td>${row.changed_positions}</td><td>${row.kendall_tau.toFixed(2)}</td></tr>`)
    .join('')
  const knowledgeMetrics = report.path_impact.knowledge_metrics
  const knowledgeRows = knowledgeMetrics
    ? knowledgeMetrics.by_profile
      .map((row) => `<tr><td>${esc(row.name)}</td><td>${evalPercent(row.full.prerequisite_violation_rate)}</td><td>${row.full.target_covered}/${row.full.target_total}（${evalPercent(row.full.target_coverage)}）</td><td>${evalPercent(row.full.difficulty_smoothness)}</td><td>${evalPercent(row.full.time_fit)}</td><td>${evalPercent(row.baseline.prerequisite_violation_rate)}</td></tr>`)
      .join('')
    : ''
  const knowledgeSection = knowledgeMetrics
    ? `<h2>路径质量指标（真实知识点路线）</h2>
<table><thead><tr><th>学生类型</th><th>先修违规率</th><th>目标覆盖</th><th>难度平滑度</th><th>时长贴合度</th><th>对照：不用图谱违规率</th></tr></thead><tbody>${knowledgeRows}</tbody></table>
<p>三类学生路线平均差异度 ${evalPercent(knowledgeMetrics.divergence.average_difference)}，数值越高说明不同基础的学生拿到的顺序越不一样。</p>
<p class="note">${esc(knowledgeMetrics.method_note)}</p>`
    : ''
  const coverage = report.coverage.per_node
    .map((row) => `<tr><td>${esc(row.name)}</td><td>${row.projects}</td><td>${row.quiz_questions}</td><td>${row.tutorial_docs}</td><td>${row.has_description ? '有' : '无'}</td><td>${row.similar_count}</td></tr>`)
    .join('')
  const gold = report.edge_quality.gold
  const goldSection = gold && gold.available
    ? `<h2>独立金标准对照</h2>
<p>金标准 ${esc(gold.version)}（${esc(gold.status_label)}）：共 ${gold.labels_total} 条边，正例 ${gold.positive_total} 条、负例 ${gold.negative_total} 条；AI 边被判定 ${gold.ai_labeled} 条（命中正例 ${gold.ai_positive_hits}、命中负例 ${gold.ai_negative_hits}），未覆盖 ${gold.ai_unlabeled} 条。</p>
<p>严格精确率 ${evalPercent(gold.strict_precision)}（未覆盖按错误计，保守下限）；判定精确率 ${evalPercent(gold.judged_precision)}；新增正例召回 ${evalPercent(gold.ai_recall_novel)}；整张图谱覆盖金标准正例 ${evalPercent(gold.graph_coverage)}（核心 ${evalPercent(gold.graph_core_coverage)}、补充 ${evalPercent(gold.graph_extended_coverage)}）。</p>
<p>双人标注一致性 kappa：${gold.kappa === null ? '待补（第二位标注者尚未填写）' : gold.kappa}</p>
<p class="note">${esc(gold.detail)}</p>`
    : ''
  const stability = report.edge_quality.stability
  const stabilitySection = stability && stability.status === 'sampled'
    ? `<h2>多次生成稳定性</h2><p>已抽检 ${stability.runs} 次生成，两两 Jaccard 相似度均值 ${evalPercent(stability.mean_jaccard)}（最低 ${evalPercent(stability.min_jaccard)}、最高 ${evalPercent(stability.max_jaccard)}）。</p>`
    : `<h2>多次生成稳定性</h2><p class="note">${esc((stability && stability.detail) || '未抽检')}</p>`
  const recommendations = (report.recommendations || []).map((item) => `<li>${esc(item)}</li>`).join('')
  const html = `<!doctype html><html lang="zh-CN"><head><meta charset="utf-8"><title>知识图谱测评报告</title>
<style>
body{font-family:"Microsoft YaHei",system-ui,sans-serif;color:#1f2430;margin:32px;line-height:1.6}
h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:22px 0 8px;border-left:4px solid #4c7ff0;padding-left:8px}
.score{font-size:40px;font-weight:700;color:#2f6df6}.grade{margin-left:8px;font-size:16px;color:#4c7ff0}
.meta{color:#6b7280;font-size:12px}table{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}
th,td{border:1px solid #dfe3ec;padding:6px 8px;text-align:left}th{background:#f4f6fb}
.dims{display:flex;gap:10px;margin-top:12px}.dims div{border:1px solid #dfe3ec;border-radius:8px;padding:8px 12px;flex:1}
.dims b{display:block;font-size:20px}.dims small{color:#6b7280}
ul{padding-left:18px}li{margin:4px 0}.note{color:#6b7280;font-size:12px}
</style></head><body>
<h1>知识图谱测评报告</h1>
<div class="meta">图谱版本 ${esc(report.graph_version)} ｜ 生成时间 ${esc(formatEvalTime(report.generated_at))} ｜ ${report.has_graph ? 'AI 图谱' : '专家骨架'} ｜ ${report.node_count} 个知识点 · ${report.structure.prerequisite} 条先修关系</div>
<div class="score">${Math.round(report.summary.score)} 分<span class="grade">${esc(report.summary.grade)}</span></div>
<p>${esc(report.summary.headline)}</p>
<div class="dims">${dims}</div>
<h2>检查项</h2><table><thead><tr><th>结果</th><th>检查项</th><th>数值</th><th>说明</th></tr></thead><tbody>${checks}</tbody></table>
<h2>结构调整</h2><p>${esc(report.structure.nodes)} 个知识点、${esc(report.structure.edges)} 条关系；孤立点 ${report.structure.isolated_nodes.length} 个、悬挂边 ${report.structure.dangling_edges.length} 条、自环 ${report.structure.self_loops.length} 处、重复边 ${report.structure.duplicate_edges.length} 条、环 ${report.structure.cycles.length} 个；描述覆盖率 ${Math.round(report.structure.description_coverage * 100)}%。</p>
<h2>边质量</h2><p>${esc(report.edge_quality.detail)}</p>
<p>专家边保留率 ${evalPercent(report.edge_quality.expert_retention)}；AI 新增 ${report.edge_quality.ai_edges} 条；审核采纳 ${report.edge_quality.review.accepted} / 拒绝 ${report.edge_quality.review.rejected} / 待审 ${report.edge_quality.review.pending}；精确率 ${evalPercent(report.edge_quality.precision)}（${esc(evalPrecisionLabel(report.edge_quality.precision_source))}）、召回率 ${evalPercent(report.edge_quality.recall)}、F1 ${evalPercent(report.edge_quality.f1)}。</p>
<p class="note">${esc(report.edge_quality.method_note)}</p>
${goldSection}
${stabilitySection}
<h2>路径影响（模拟 3 类学生）</h2><table><thead><tr><th>学生类型</th><th>拦截快进</th><th>补先修</th><th>顺序变化</th><th>顺序一致性 τ</th></tr></thead><tbody>${profiles}</tbody></table>
${knowledgeSection}
<h2>证据覆盖</h2><table><thead><tr><th>知识点</th><th>项目</th><th>测评题</th><th>教程</th><th>AI 描述</th><th>相似边</th></tr></thead><tbody>${coverage}</tbody></table>
<h2>改进建议</h2><ul>${recommendations}</ul>
</body></html>`
  const win = window.open('', '_blank')
  if (!win) {
    ElMessage.warning('浏览器拦住了新窗口，请允许弹窗后再试')
    return
  }
  win.document.write(html)
  win.document.close()
  win.focus()
  win.onload = () => win.print()
}

async function reviewEdge(edge, action) {
  if (!edge || reviewingEdge.value) return
  reviewingEdge.value = edge.key || `${edge.source}-${edge.target}-${edge.relation}`
  try {
    const data = await reviewKnowledgeGraphEdge({
      source: edge.source,
      target: edge.target,
      relation: edge.relation || 'prerequisite',
      action,
    })
    if (data) graph.value = data
    ElMessage.success(
      action === 'accept'
        ? '已采纳这条先修关系，它会参与学习路径编排'
        : '已拒绝这条关系，它不再影响学习顺序',
    )
    await loadGraph(graphScope.value)
    await nextTick()
    renderActive()
    bindResize()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '审核知识关系失败')
  } finally {
    reviewingEdge.value = ''
  }
}

async function load() {
  loading.value = true
  try {
    const data = await getLearningRoadmap()
    hasPath.value = !!data?.has_path
    roadmap.value = data?.has_path ? data : null
    availableTracks.value = data?.available_tracks || []
    if (hasPath.value) {
      await nextTick()
      renderActive()
      bindResize()
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '获取学习地图失败')
  } finally {
    loading.value = false
  }
}

function clearQuizAnswers() {
  Object.keys(quizAnswers).forEach(key => delete quizAnswers[key])
  Object.keys(quizMultiAnswers).forEach(key => delete quizMultiAnswers[key])
}

async function fetchQuiz(params, fallbackMessage) {
  quizLoading.value = true
  quizQuestions.value = []
  quizSessionId.value = null
  clearQuizAnswers()
  try {
    const data = await startQuickQuiz(params)
    quizSessionId.value = data?.session_id || null
    quizQuestions.value = data?.questions || []
    if (!quizQuestions.value.length) {
      ElMessage.warning(fallbackMessage)
    }
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || fallbackMessage)
  } finally {
    quizLoading.value = false
  }
}

async function openQuickQuiz() {
  quizMode.value = 'placement'
  quizFocusTag.value = ''
  quizVisible.value = true
  await fetchQuiz({}, '暂时没有拿到题目，可以先跳过测评直接生成')
}

async function openNodeQuiz(tag) {
  quizMode.value = 'diagnose'
  quizFocusTag.value = tag
  quizVisible.value = true
  await fetchQuiz({ knowledge_tag: tag }, '这个知识点暂时没有题目，可以先学教程或做代码实验')
}

async function submitQuickQuiz() {
  if (!quizSessionId.value) {
    ElMessage.warning('题目还没准备好，请稍后再试')
    return
  }
  const answerList = quizQuestions.value.map((q) => {
    const value = quizMultiAnswers[q.question_id] ?? quizAnswers[q.question_id]
    return {
      question_id: q.question_id,
      user_answer: Array.isArray(value) ? value.join(',') : (value || ''),
    }
  })

  if (quizMode.value === 'diagnose') {
    if (!answerList.some((item) => item.user_answer)) {
      ElMessage.info('请先选一个答案再提交，这样才会计入练习证据')
      return
    }
    quizSubmitting.value = true
    try {
      const result = await submitQuickQuizApi({ session_id: quizSessionId.value, answers: answerList })
      const replan = result?.path_replan
      if (replan?.applied) {
        ElMessage.success({
          message: `掌握度已更新，路线也跟着调整了。${replan.message || ''}`,
          duration: 6000,
        })
      } else {
        ElMessage.success('已记录，这个知识点的掌握度已更新')
      }
      quizVisible.value = false
      detailVisible.value = false
      await load()
      await loadGraph(graphScope.value)
      await nextTick()
      renderActive()
      bindResize()
    } catch (error) {
      ElMessage.error(error?.response?.data?.message || '提交测评失败，请稍后再试')
    } finally {
      quizSubmitting.value = false
    }
    return
  }

  if (!answerList.some((item) => item.user_answer)) {
    ElMessage.info(`这 ${quizQuestions.value.length} 题都空着，将按注册信息先估一个水平`)
    await generatePath()
    return
  }
  quizSubmitting.value = true
  try {
    await submitQuickQuizApi({ session_id: quizSessionId.value, answers: answerList })
    localStorage.setItem('last_quick_quiz_session_id', String(quizSessionId.value))
    await generatePath(quizSessionId.value)
    if (hasPath.value) quizVisible.value = false
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '提交测评失败，可以先跳过测评直接生成')
  } finally {
    quizSubmitting.value = false
  }
}

async function generatePath(diagnosticSessionId = null) {
  const preferences = loadStoredPreferences()
  generating.value = true
  try {
    await generateLearningPath({
      modules: availableTracks.value,
      learning_depth: '标准',
      diagnostic_session_id: diagnosticSessionId,
      target_tags: preferences.target_tags,
      weekly_hours: preferences.weekly_hours,
      deadline_weeks: preferences.deadline_weeks,
      preferred_mode: preferences.preferred_mode,
    })
    ElMessage.success(diagnosticSessionId ? '已按测评结果生成学习路线' : '已生成学习路线')
    quizVisible.value = false
    await load()
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '生成学习路线失败')
  } finally {
    generating.value = false
  }
}

async function regeneratePath() {
  try {
    await ElMessageBox.confirm(
      '重新生成会清空当前的任务进度，但会按你最新的学习情况重新调整路线。确定继续吗？',
      '重新生成学习路线',
      { type: 'warning', confirmButtonText: '继续', cancelButtonText: '取消' },
    )
  } catch {
    return
  }
  regenerating.value = true
  try {
    const lastQuizSessionId = Number(localStorage.getItem('last_quick_quiz_session_id')) || null
    await deleteLearningPath()
    hasPath.value = false
    roadmap.value = null
    await load()
    await generatePath(lastQuizSessionId)
  } catch (error) {
    ElMessage.error(error?.response?.data?.message || '重置学习路线失败')
  } finally {
    regenerating.value = false
  }
}

function goStation(station) {
  if (station.module_id && station.lab_id) {
    router.push(`/code-lab/${station.module_id}/${station.lab_id}`)
    return
  }
  goDoc(station)
}

function goProject(project) {
  if (!project) return
  if (project.module_id && project.lab_id) {
    router.push(`/code-lab/${project.module_id}/${project.lab_id}`)
    return
  }
  router.push(project.topic ? { path: '/learning-docs', query: { knowledge: project.topic } } : '/learning-docs')
}

function goDoc(station) {
  router.push(station.knowledge ? { path: '/learning-docs', query: { knowledge: station.knowledge } } : '/learning-docs')
}

function goKnowledgeDoc(unit) {
  router.push(unit?.tag ? { path: '/learning-docs', query: { knowledge: unit.tag } } : '/learning-docs')
}

function goKnowledgeLab(unit) {
  const project = unit?.project
  if (project?.module_id && project?.lab_id) {
    router.push(`/code-lab/${project.module_id}/${project.lab_id}`)
    return
  }
  goKnowledgeDoc(unit)
}

function openKnowledgeQuiz(unit) {
  if (!unit?.tag) return
  openNodeQuiz(unit.tag)
}

onMounted(async () => {
  resizeObserver = new ResizeObserver(() => {
    chart?.resize()
    graphChart?.resize()
  })
  await load()
})

onBeforeUnmount(() => {
  resizeObserver?.disconnect()
  disposeCharts()
})
</script>

<style scoped>
.learning-path-page { display: flex; flex-direction: column; gap: 16px; }

.empty-actions { display: flex; flex-wrap: wrap; gap: 12px; justify-content: center; }
.quiz-hint { margin: 0 0 16px; color: #66708a; font-size: 13px; line-height: 1.6; }
.quiz-loading { min-height: 180px; }
.quiz-item { padding: 12px 0; border-bottom: 1px solid #eef1f7; }
.quiz-item:last-child { border-bottom: 0; }
.quiz-item h4 { margin: 0 0 10px; font-size: 14px; font-weight: 600; color: #1f2a44; line-height: 1.6; }
.quiz-item :deep(.el-radio-group),
.quiz-item :deep(.el-checkbox-group) { display: flex; flex-direction: column; align-items: flex-start; gap: 6px; }

.view-switch {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  border: 1px solid #e2e7f1;
  border-radius: 12px;
  background: #f4f7fc;
  align-self: flex-start;
}
.view-tab {
  padding: 6px 16px;
  border: 0;
  border-radius: 9px;
  background: transparent;
  color: #71809b;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all .18s;
}
.view-tab:hover { color: #4c7ff0; }
.view-tab.active { background: #fff; color: #17213a; box-shadow: 0 2px 8px rgba(24, 38, 72, .1); }

.notice-strip {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 12px 16px;
  border: 1px solid #f3d9cf;
  border-radius: 14px;
  background: linear-gradient(100deg, #fff7f3, #fffdfb);
}
.notice-dot { width: 8px; height: 8px; flex: 0 0 8px; margin-top: 6px; border-radius: 50%; background: #ff8c73; }
.notice-strip strong { color: #c05238; font-size: 13px; }
.notice-strip p { margin: 3px 0 0; color: #8a6a5f; font-size: 12px; }

.graph-impact-strip {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 14px;
  padding: 12px 16px;
  border: 1px solid #cfe3d8;
  border-radius: 14px;
  background: linear-gradient(100deg, #f5fbf7, #fbfefc);
}
.impact-copy { display: flex; flex-direction: column; gap: 3px; flex: 1 1 260px; }
.impact-copy b { color: #23734f; font-size: 13px; }
.impact-copy span { color: #6d8a7b; font-size: 11.5px; line-height: 1.6; }
.impact-metrics { display: flex; flex-wrap: wrap; gap: 8px; }
.impact-metrics span {
  padding: 3px 9px;
  border-radius: 8px;
  background: #fff;
  border: 1px solid #dcebe2;
  color: #5b7a68;
  font-size: 11.5px;
}
.impact-metrics b { color: #23734f; font-size: 12.5px; }
.impact-links {
  margin: 4px 0 0;
  padding-left: 16px;
  color: #5b7a68;
  font-size: 11.5px;
  line-height: 1.7;
}
.impact-links b { color: #23734f; font-size: 11.5px; }

.summary-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); }
.summary-card {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 15px 17px;
  border: 1px solid #e2e7f1;
  border-radius: 16px;
  background: #fff;
  box-shadow: var(--shadow-sm, 0 4px 14px rgba(24, 38, 72, .06));
}
.summary-card small { color: #8a95a8; font-size: 11px; letter-spacing: .04em; }
.summary-card b { color: #17213a; font-size: 22px; font-weight: 760; letter-spacing: -.02em; }
.summary-card span { color: #8a95a8; font-size: 11px; }

/* ---------- 学习者画像 / 备选方案（#43 #44） ---------- */
.profile-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; }
.profile-head h2 { margin: 0; color: #17213a; font-size: 15px; font-weight: 720; }
.profile-head p { margin: 4px 0 0; color: #8a95a8; font-size: 11.5px; line-height: 1.6; }
.profile-tags { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 12px; }
.profile-chip {
  padding: 4px 10px;
  border-radius: 999px;
  border: 1px solid #e3e8f2;
  background: #f7f9fd;
  color: #69748c;
  font-size: 11.5px;
}
.profile-chip b { color: #2b3550; }
.profile-notes { display: flex; flex-direction: column; gap: 6px; margin-top: 12px; }
.profile-notes p { margin: 0; color: #5b6579; font-size: 11.5px; line-height: 1.75; }
.profile-notes b { color: #2b3550; }
.profile-em {
  margin: 0 3px;
  padding: 1px 7px;
  border-radius: 6px;
  background: #fff3ef;
  color: #c05038;
  font-style: normal;
}
.alt-grid { display: grid; gap: 12px; grid-template-columns: repeat(auto-fit, minmax(240px, 1fr)); }
.alt-item {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 14px 15px;
  border: 1px solid #e2e7f1;
  border-radius: 14px;
  background: #fbfcfe;
}
.alt-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
.alt-head b { color: #17213a; font-size: 13px; font-weight: 720; }
.alt-points { margin: 0; padding-left: 16px; color: #5b6579; font-size: 11.5px; line-height: 1.8; }
.alt-foot { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-top: auto; }
.alt-foot span { color: #8a95a8; font-size: 11px; }
.pref-hint { margin: 0 0 14px; color: #66708a; font-size: 12.5px; line-height: 1.7; }
.pref-note { margin: 4px 0 0; color: #98a2b5; font-size: 11.5px; line-height: 1.6; }
.pref-select { width: 100%; }
.pref-unit { margin-left: 8px; color: #8a95a8; font-size: 12px; }

.map-card,
.graph-card,
.progress-card,
.history-card,
.profile-card,
.alt-card,
.knowledge-card {
  padding: 16px 18px 18px;
  border: 1px solid #e2e7f1;
  border-radius: 18px;
  background: #fff;
  box-shadow: var(--shadow-sm, 0 4px 14px rgba(24, 38, 72, .06));
}
.card-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 12px; margin-bottom: 10px; }
.card-head h2 { margin: 0; color: #17213a; font-size: 15px; font-weight: 720; }
.card-head p { margin: 4px 0 0; color: #8a95a8; font-size: 11.5px; line-height: 1.6; }
.legend { display: flex; flex-wrap: wrap; gap: 12px; }
.legend-item { display: inline-flex; align-items: center; gap: 5px; color: #5b6579; font-size: 11.5px; }
.legend-item i { display: inline-block; width: 10px; height: 10px; border-radius: 3px; }
.legend-ring { border-radius: 50%; background: transparent !important; }
.legend-ring.current { border: 3px solid #ff6b4a; }
.legend-ring.done { border: 3px solid #2f9e6b; }
.legend-ring.frontier { border: 3px solid #2f9e9e; }

.map-scroll { overflow-x: auto; }
.map-canvas { width: 100%; }

/* ---------- 知识图谱 ---------- */
.graph-card .legend-item i { border-radius: 50%; box-shadow: 0 2px 6px rgba(24, 38, 72, .18); }
.legend-line { width: 16px !important; height: 0 !important; border-radius: 0 !important; box-shadow: none !important; }
.legend-line.expert { border-top: 2px solid #5d6b82; }
.legend-line.ai { border-top: 2px solid #2f9e9e; }
.legend-line.pending { border-top: 2px dashed #e08a3c; }
.legend-line.similar { border-top: 2px dashed #a97fe6; }
.legend-line.part-of { border-top: 2px dotted #8a96ad; }
.graph-scope {
  margin-left: 8px;
  padding: 1px 7px;
  border-radius: 7px;
  background: #eef4ff;
  color: #5b7291;
  font-size: 10.5px;
  font-weight: 600;
}

.graph-bar { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 8px; }
.graph-tip { color: #9aa4b6; font-size: 11.5px; }
.graph-query {
  display: grid;
  gap: 8px;
  margin-bottom: 10px;
  padding: 10px 12px;
  border: 1px solid #e8edf7;
  border-radius: 12px;
  background: #fbfcff;
}
.gq-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.gq-label { min-width: 48px; color: #5b7291; font-size: 12px; font-weight: 600; }
.gq-input { width: 200px; }
.gq-arrow { color: #9aa4b6; font-size: 13px; }
.gq-result { padding-top: 6px; border-top: 1px dashed #e8edf7; }
.gq-summary { margin: 0 0 6px; color: #48566f; font-size: 12.5px; }
.gq-summary b { color: #2f6bd8; }
.gq-group { display: flex; flex-wrap: wrap; align-items: flex-start; gap: 8px; margin-bottom: 6px; }
.gq-hop { color: #71809b; font-size: 11.5px; line-height: 24px; }
.gq-tags { display: flex; flex-wrap: wrap; gap: 6px; }
.gq-tag { cursor: pointer; }
.gq-chain { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; margin-bottom: 6px; }
.gq-node {
  padding: 2px 9px;
  border: 1px solid #dbe6fb;
  border-radius: 8px;
  background: #f4f8ff;
  color: #2f6bd8;
  font-size: 12px;
  cursor: pointer;
}
.gq-steps { margin: 0; padding-left: 18px; color: #71809b; font-size: 11.5px; line-height: 1.8; }
.gq-empty, .gq-hint { margin: 0; color: #9aa4b6; font-size: 11.5px; }
.graph-notice {
  margin: 0 0 10px;
  padding: 9px 12px;
  border: 1px solid #dbe6fb;
  border-radius: 11px;
  background: #f4f8ff;
  color: #5b7291;
  font-size: 12px;
  line-height: 1.6;
}
.counterfactual-card {
  margin-bottom: 14px;
  padding: 14px 16px;
  border: 1px solid #f3ddc8;
  border-radius: 14px;
  background: linear-gradient(180deg, #fffaf4 0%, #ffffff 70%);
}
.cf-head { display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: space-between; gap: 10px; margin-bottom: 10px; }
.cf-head h2 { margin: 0 0 4px; color: #2b3446; font-size: 15px; }
.cf-head p { margin: 0; color: #8a7358; font-size: 12px; line-height: 1.6; }
.cf-options { display: grid; gap: 8px; margin: 0 0 10px; padding: 0; list-style: none; }
.cf-item {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border: 1px solid #ece4d9;
  border-radius: 11px;
  background: #fff;
}
.cf-item.best { border-color: #f0b27a; box-shadow: 0 2px 10px rgba(224, 138, 60, 0.12); }
.cf-rank {
  flex: none;
  padding: 2px 8px;
  border-radius: 7px;
  background: #fdf0e3;
  color: #c2702a;
  font-size: 11px;
  font-weight: 700;
}
.cf-item.best .cf-rank { background: #f4a259; color: #fff; }
.cf-main { flex: 1 1 200px; min-width: 160px; }
.cf-name { display: flex; align-items: baseline; gap: 8px; color: #2b3446; font-size: 13px; }
.cf-name em { color: #9aa4b6; font-size: 11px; font-style: normal; }
.cf-main p { margin: 3px 0 0; color: #71809b; font-size: 11.5px; line-height: 1.65; }
.cf-metrics { display: flex; flex-wrap: wrap; align-items: center; gap: 6px 12px; color: #71809b; font-size: 11.5px; }
.cf-metrics b { color: #2f9e6b; }
.cf-cost { color: #9aa4b6; }
.cf-note { margin: 0; color: #9aa4b6; font-size: 11px; line-height: 1.7; }
.discarded-box {
  margin: 0 0 10px;
  padding: 8px 12px;
  border: 1px solid #e6eaf2;
  border-radius: 10px;
  background: #fafbfd;
  color: #71809b;
  font-size: 11.5px;
  line-height: 1.7;
}
.discarded-box summary { cursor: pointer; color: #5b7291; font-weight: 600; }
.discarded-box ul { margin: 6px 0 0; padding-left: 18px; }
.graph-scroll {
  overflow: hidden;
  border: 1px solid #e8edf7;
  border-radius: 14px;
  background: #fbfcff;
}
.graph-canvas { width: 100%; height: 620px; }

.node-detail { display: flex; flex-direction: column; gap: 14px; }
.detail-head { display: flex; align-items: center; gap: 8px; }
.detail-head code { padding: 2px 7px; border-radius: 6px; background: #f1f4fa; color: #71809b; font-size: 11.5px; }
.detail-def { margin: 0; color: #3c4658; font-size: 13px; line-height: 1.75; }
.detail-block { display: flex; flex-direction: column; gap: 6px; }
.detail-block > b { color: #17213a; font-size: 12.5px; font-weight: 700; }
.detail-block ul { margin: 0; padding-left: 18px; color: #4a5568; font-size: 12.5px; line-height: 1.8; }
.readiness-block { padding: 10px 12px; border: 1px solid #e4eaf5; border-radius: 10px; background: #f8faff; }
.readiness-row { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.readiness-score { color: #8a95a8; font-size: 11.5px; }
.readiness-blockers { margin: 0; color: #c05038; font-size: 12px; line-height: 1.65; }
.readiness-blockers.ok { color: #2f9e6b; }
.readiness-blockers.warn { color: #b57a2a; }
.rel-list { padding-left: 0 !important; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.rel-list li { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.rel-link {
  padding: 0;
  border: 0;
  background: transparent;
  color: #4c7ff0;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}
.rel-link:hover { text-decoration: underline; }
.rel-origin { padding: 1px 6px; border-radius: 6px; font-size: 10.5px; }
.rel-origin.expert { background: #eef3fb; color: #5b7291; }
.rel-origin.llm { background: #f4eefc; color: #8a5cd0; }
.rel-list small { flex: 1 1 100%; color: #9aa4b6; font-size: 11px; }
.rel-empty { margin: 0; color: #b3bbca; font-size: 12px; }
.mastery-line { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; color: #4a5568; font-size: 12.5px; }
.mastery-line b { color: #17213a; font-size: 14px; }
.detail-hint { margin: 0; color: #8a95a8; font-size: 11.5px; line-height: 1.65; }
.detail-evidence { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; margin: 6px 0 4px; color: #5b687f; font-size: 11.5px; }
.chip-row { display: flex; flex-wrap: wrap; gap: 6px; }
.chip {
  padding: 3px 9px;
  border: 1px solid #dbe3f2;
  border-radius: 999px;
  background: #f7f9fe;
  color: #4c7ff0;
  font-size: 11.5px;
  cursor: pointer;
}
.chip:hover { border-color: #a9c3f2; background: #eef4ff; }
.parent-list,
.project-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.parent-list li,
.project-list li {
  display: flex;
  flex-direction: column;
  gap: 3px;
  padding: 8px 10px;
  border: 1px solid #eef1f7;
  border-radius: 10px;
  background: #fbfcfe;
}
.parent-head,
.project-head { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; }
.parent-meta { color: #8a95a8; font-size: 11px; }
.parent-warn { color: #b57a2a; font-size: 11px; }
.parent-evidence { color: #9aa4b6; font-size: 11px; }
.project-topic { color: #17213a; font-size: 12.5px; font-weight: 650; }
.project-list small { color: #9aa4b6; font-size: 11px; }
.rel-confidence { padding: 1px 6px; border-radius: 6px; background: #eef7f7; color: #2f8f8f; font-size: 10.5px; }
.rel-review { padding: 1px 6px; border-radius: 6px; font-size: 10.5px; }
.rel-review.accepted { background: #eefaf3; color: #2f9e6b; }
.rel-review.pending { background: #fff4e8; color: #c2742a; }
.rel-review.rejected { background: #f2f4f8; color: #9aa4b6; }
.rel-evidence { color: #9aa4b6 !important; }
.rel-actions { display: inline-flex; gap: 2px; flex: 1 1 100%; }

.phase-block { padding: 12px 0; border-top: 1px solid #eef1f7; }
.phase-block:first-of-type { border-top: 0; }
.phase-head { display: flex; flex-wrap: wrap; align-items: center; gap: 10px; }
.phase-head b { color: #17213a; font-size: 13px; font-weight: 700; }
.phase-head span { color: #8a95a8; font-size: 11.5px; }
.phase-bar { flex: 1 1 160px; min-width: 120px; }

.station-list { margin: 10px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.station-row {
  display: grid;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #eef1f7;
  border-radius: 12px;
  background: #fbfcfe;
  grid-template-columns: 66px minmax(180px, 1fr) auto auto auto auto auto;
}
.station-row.is-current { border-color: #f6c9b9; background: #fff9f6; }
.station-row.is-locked { opacity: .72; }
.station-day { color: #8a95a8; font-size: 11.5px; }
.station-title { display: flex; flex-direction: column; min-width: 0; }
.station-title b { overflow: hidden; color: #17213a; font-size: 12.5px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }
.station-title small { color: #9aa4b6; font-size: 10.5px; }
.station-title small.station-blockers { overflow: hidden; color: #d06a4a; text-overflow: ellipsis; white-space: nowrap; }
.station-tags { display: inline-flex; flex-wrap: wrap; gap: 4px; }
.mini-tag { padding: 2px 7px; border-radius: 7px; font-size: 10.5px; font-style: normal; white-space: nowrap; }
.mini-tag.remedial { background: #fff2e8; color: #c2612f; border: 1px solid #f6d8c3; }
.mini-tag.gated { background: #fdf0ee; color: #c05038; border: 1px solid #f3d3cb; }
.mini-tag.skip { background: #eefaf3; color: #2f9e6b; border: 1px solid #cceadb; }
.band-tag { border: 0; }
.station-sub { display: inline-flex; gap: 6px; }
.station-sub i { padding: 2px 7px; border: 1px solid #e2e7f1; border-radius: 7px; color: #a3abbb; font-size: 10.5px; font-style: normal; }
.station-sub i.on { border-color: #bfe3d1; color: #2f9e6b; background: #f1faf5; }
.station-status { font-size: 11.5px; color: #8a95a8; }
.station-status.is-done { color: #2f9e6b; }
.station-status.is-current { color: #ff6b4a; font-weight: 650; }
.station-actions { display: inline-flex; gap: 2px; justify-self: end; }

/* ---------- 路线变更记录 ---------- */
.history-count {
  padding: 2px 8px;
  border-radius: 8px;
  background: #eef4ff;
  color: #5b7291;
  font-size: 10.5px;
  font-weight: 600;
}
.history-list { margin: 4px 0 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 8px; }
.history-row {
  padding: 11px 14px;
  border: 1px solid #eef1f7;
  border-radius: 12px;
  background: #fbfcfe;
}
.history-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.history-version {
  padding: 1px 7px;
  border-radius: 7px;
  background: #17213a;
  color: #fff;
  font-size: 11px;
  font-weight: 700;
}
.history-trigger { color: #38445c; font-size: 12px; font-weight: 650; }
.history-time { margin-left: auto; color: #9aa4b6; font-size: 10.5px; }
.history-summary { margin: 6px 0 0; color: #5b6579; font-size: 12px; line-height: 1.6; }
.history-changes { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 7px; }
.history-change {
  padding: 2px 8px;
  border: 1px solid #dbe6fb;
  border-radius: 8px;
  background: #f4f8ff;
  color: #45618c;
  font-size: 10.5px;
}
.history-diff { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 6px; }
.history-diff em {
  padding: 2px 8px;
  border-radius: 8px;
  background: #f1faf5;
  color: #2f7d5b;
  font-size: 10.5px;
  font-style: normal;
}

/* ---------- 知识图谱测评 ---------- */
.eval-body { min-height: 200px; }
.version-body { min-height: 160px; }
.version-tip { margin: 0 0 12px; padding: 9px 12px; border: 1px solid #dbe6fb; border-radius: 10px; background: #f4f8ff; color: #5b7291; font-size: 12px; line-height: 1.65; }
.version-list { margin: 0; padding: 0; list-style: none; display: grid; gap: 10px; }
.version-item { padding: 10px 12px; border: 1px solid #e6eaf2; border-radius: 11px; background: #fff; }
.version-item.current { border-color: #b9e3cd; background: #f7fdf9; }
.version-head { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-bottom: 4px; }
.version-head b { color: #1f2430; font-size: 13px; }
.version-note { margin: 0 0 4px; color: #48566f; font-size: 12px; line-height: 1.6; }
.version-meta { margin: 0 0 8px; color: #9aa4b6; font-size: 11.5px; }
.version-empty { margin: 0; color: #9aa4b6; font-size: 12px; }
.eval-hero { display: flex; gap: 16px; align-items: center; padding: 14px 16px; border: 1px solid #e2e7f1; border-radius: 12px; background: linear-gradient(135deg, #f7f9ff, #fff); }
.eval-score { display: flex; flex-direction: column; align-items: center; justify-content: center; min-width: 92px; padding: 8px 12px; border-radius: 10px; background: #eef3ff; color: #2f6df6; }
.eval-score b { font-size: 32px; line-height: 1.1; }
.eval-score span { font-size: 11px; color: #7d8aa5; }
.eval-score em { margin-top: 2px; font-size: 12px; font-style: normal; font-weight: 650; }
.eval-score.excellent { background: #eefaf3; color: #2f9e6b; }
.eval-score.good { background: #eef3ff; color: #2f6df6; }
.eval-score.pass { background: #fff7e8; color: #c8862f; }
.eval-score.weak { background: #fdf0ee; color: #c05038; }
.eval-headline { flex: 1; }
.eval-headline p { margin: 0 0 8px; color: #38445c; font-size: 13px; line-height: 1.65; }
.eval-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; color: #8a95a8; font-size: 11.5px; }
.eval-dims { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-top: 12px; }
.eval-dim { display: flex; flex-direction: column; padding: 10px 12px; border: 1px solid #e2e7f1; border-radius: 10px; background: #fff; }
.eval-dim span { color: #6b7891; font-size: 12px; }
.eval-dim b { margin: 2px 0; color: #1f2430; font-size: 22px; }
.eval-dim b.na { color: #b3bbca; }
.eval-dim em { color: #9aa4b6; font-size: 11px; font-style: normal; }
.eval-block { margin-top: 18px; }
.eval-block h4 { margin: 0 0 8px; padding-left: 8px; border-left: 3px solid #4c7ff0; color: #1f2430; font-size: 13.5px; }
.eval-detail { margin: 0 0 6px; color: #5b687f; font-size: 12.5px; line-height: 1.7; }
.eval-subtitle { margin: 10px 0 2px; color: #1f2430; font-size: 12.5px; font-weight: 600; }
.eval-note { color: #9aa4b6; font-size: 11.5px; line-height: 1.6; }
.metric-list, .recommend-list { margin: 6px 0 0; padding-left: 18px; color: #5b687f; font-size: 12.5px; line-height: 1.8; }
.metric-list b { color: #1f2430; }
.check-list { margin: 0; padding: 0; list-style: none; }
.check-list li { display: flex; gap: 10px; padding: 8px 0; border-bottom: 1px dashed #eef1f7; }
.check-list li:last-child { border-bottom: 0; }
.check-list li i { flex: none; width: 20px; height: 20px; border-radius: 50%; font-size: 12px; font-style: normal; font-weight: 700; line-height: 20px; text-align: center; }
.check-list li.pass i { background: #eefaf3; color: #2f9e6b; }
.check-list li.warn i { background: #fff7e8; color: #c8862f; }
.check-list li.fail i { background: #fdf0ee; color: #c05038; }
.check-list li b { color: #2b3445; font-size: 12.5px; }
.check-value { margin-left: 8px; color: #8a95a8; font-size: 11.5px; }
.check-list li p { margin: 2px 0 0; color: #7c879b; font-size: 11.5px; line-height: 1.6; }
.eval-table { margin-top: 6px; }
.eval-actions { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 20px; padding-top: 14px; border-top: 1px solid #eef1f7; }

/* ---------- 知识点路线 ---------- */
.knowledge-card { display: flex; flex-direction: column; gap: 14px; }
.knowledge-next {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 14px 16px;
  border: 1px solid #f6c9b9;
  border-radius: 14px;
  background: linear-gradient(135deg, #fff9f6, #fff);
}
.knowledge-next-copy small { color: #c2612f; font-size: 11px; letter-spacing: .06em; }
.knowledge-next-copy h3 { margin: 4px 0 2px; color: #17213a; font-size: 17px; }
.knowledge-next-copy p { margin: 0; color: #7c879b; font-size: 12px; line-height: 1.6; }
.knowledge-next-blockers { color: #d06a4a !important; }
.knowledge-next-actions { display: inline-flex; flex-wrap: wrap; gap: 6px; }
.knowledge-summary { margin: 0; }
.knowledge-list { margin: 0; padding: 0; list-style: none; display: flex; flex-direction: column; gap: 6px; }
.knowledge-row {
  display: grid;
  align-items: center;
  gap: 10px;
  padding: 9px 12px;
  border: 1px solid #eef1f7;
  border-radius: 12px;
  background: #fbfcfe;
  grid-template-columns: 34px minmax(180px, 1fr) auto auto auto;
}
.knowledge-row.is-done { background: #f8fdfa; }
.knowledge-row.is-current { border-color: #f6c9b9; background: #fff9f6; }
.knowledge-row.is-locked { opacity: .75; }
.knowledge-order {
  display: inline-flex;
  width: 26px;
  height: 26px;
  align-items: center;
  justify-content: center;
  border-radius: 50%;
  background: #eef3ff;
  color: #4c7ff0;
  font-size: 11.5px;
  font-weight: 700;
}
.knowledge-row.is-done .knowledge-order { background: #eefaf3; color: #2f9e6b; }
.knowledge-row.is-current .knowledge-order { background: #ffece6; color: #e05a35; }
.knowledge-main { display: flex; flex-direction: column; min-width: 0; }
.knowledge-main b {
  overflow: hidden;
  color: #17213a;
  font-size: 12.5px;
  font-weight: 650;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.knowledge-main small { display: flex; flex-wrap: wrap; align-items: center; gap: 5px; color: #9aa4b6; font-size: 10.5px; }
.knowledge-main small em { font-style: normal; }
.mini-tag.course { background: #eef3ff; color: #4c7ff0; border: 1px solid #dbe4ff; }
.mini-tag.extension { background: #f4f6fb; color: #8a95a8; border: 1px solid #e2e7f1; }
.mini-tag.attr { background: #f7f9fd; color: #63718a; border: 1px solid #e6ebf4; }
.mini-tag.target { background: #fff5e6; color: #d98a20; border: 1px solid #f7dfb5; }
.mini-tag.error { background: #fff3ef; color: #c05038; border: 1px solid #f5d6cc; }
.mini-tag.check { background: #eef7ff; color: #3378b8; border: 1px solid #d3e6f8; }
.rel-contain { padding: 1px 6px; border-radius: 6px; font-size: 10.5px; background: #f2f4f9; color: #6c7893; border: 1px solid #e3e8f2; }
.station-status.is-locked { color: #c05038; }
.knowledge-empty { margin: 6px 0 0; color: #9aa4b6; font-size: 12px; }

@media (max-width: 900px) {
  .station-row { grid-template-columns: 1fr; gap: 6px; }
  .station-actions { justify-self: start; }
  .knowledge-row { grid-template-columns: 1fr; gap: 6px; }
}
</style>
