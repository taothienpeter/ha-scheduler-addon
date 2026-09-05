// Smart Calendar Scheduler - Dashboard Application Logic
// Supports Home Assistant Ingress and Direct Port Access

(function() {
  'use strict';

  // Base Path Resolver for Home Assistant Ingress
  const BASE_PATH = window.location.pathname.replace(/\/$/, '');
  const API_PRESETS_URL = `${BASE_PATH}/api/presets`;
  const API_SCHEDULE_URL = `${BASE_PATH}/api/schedule`;
  const API_LATEST_EXEC_URL = `${BASE_PATH}/api/latest-execution`;

  // Central Application State
  const AppState = {
    presets: {},
    currentPayload: null,
    currentResponse: null,
    latestN8nExecution: null,
    activeTierHighlight: null,
    selectedSessionId: null,
    autoSyncTimer: null
  };

  // Color Palettes for Task Sessions
  const TASK_COLORS = [
    { bg: 'linear-gradient(135deg, #6366f1, #4f46e5)', border: '#818cf8' },
    { bg: 'linear-gradient(135deg, #06b6d4, #0891b2)', border: '#22d3ee' },
    { bg: 'linear-gradient(135deg, #8b5cf6, #7c3aed)', border: '#a78bfa' },
    { bg: 'linear-gradient(135deg, #10b981, #059669)', border: '#34d399' },
    { bg: 'linear-gradient(135deg, #f59e0b, #d97706)', border: '#fbbf24' }
  ];

  // DOM Elements - Top Controls
  const elPresetSelect = document.getElementById('presetSelect');
  const elBtnOptimize = document.getElementById('btnOptimize');
  const elEngineStatusText = document.getElementById('engineStatusText');
  const elExecutionTime = document.getElementById('executionTime');
  const elHorizonBadge = document.getElementById('horizonBadge');
  const elTimelineRuler = document.getElementById('timelineRuler');
  const elTimelineTrack = document.getElementById('timelineTrack');
  const elXaiList = document.getElementById('xaiList');
  const elTooltip = document.getElementById('dashboardTooltip');

  // DOM Elements - Score Table
  const elValEnergy = document.getElementById('valEnergyBonus');
  const elValPref = document.getElementById('valPrefBonus');
  const elValSwitch = document.getElementById('valSwitchPenalty');
  const elValFrag = document.getElementById('valFragPenalty');
  const elValTardiness = document.getElementById('valTardinessPenalty');
  const elValTotal = document.getElementById('valTotalScore');

  // DOM Elements - Flow Metrics Badges
  const elMetricsT1 = document.getElementById('metricsTier1');
  const elMetricsT2 = document.getElementById('metricsTier2');
  const elMetricsT3 = document.getElementById('metricsTier3');
  const elMetricsT4 = document.getElementById('metricsTier4');
  const elMetricsT5 = document.getElementById('metricsTier5');

  // DOM Elements - n8n Execution Inspector
  const elN8nStatusBadge = document.getElementById('n8nStatusBadge');
  const elN8nTime = document.getElementById('n8nTime');
  const elN8nClientIp = document.getElementById('n8nClientIp');
  const elN8nElapsed = document.getElementById('n8nElapsed');
  const elN8nTaskCount = document.getElementById('n8nTaskCount');
  const elN8nSessionCount = document.getElementById('n8nSessionCount');
  const elN8nRequestCode = document.getElementById('n8nRequestCode');
  const elN8nTraceGrid = document.getElementById('n8nTraceGrid');
  const elN8nResponseCode = document.getElementById('n8nResponseCode');
  const elBtnFetchN8n = document.getElementById('btnFetchN8n');
  const elBtnProjectToTimeline = document.getElementById('btnProjectToTimeline');
  const elChkAutoSync = document.getElementById('chkAutoSync');
  const elBtnCopyRequest = document.getElementById('btnCopyRequest');
  const elBtnCopyResponse = document.getElementById('btnCopyResponse');

  // Init
  window.addEventListener('DOMContentLoaded', initApp);

  async function initApp() {
    setupEventListeners();
    setupN8nSection();
    await loadPresets();
    await triggerOptimization();
    await fetchLatestN8nExecution(true);
  }

  function setupEventListeners() {
    elPresetSelect.addEventListener('change', () => {
      const selectedKey = elPresetSelect.value;
      if (AppState.presets[selectedKey]) {
        AppState.currentPayload = JSON.parse(JSON.stringify(AppState.presets[selectedKey].payload));
        triggerOptimization();
      }
    });

    elBtnOptimize.addEventListener('click', () => triggerOptimization());

    // Flow Tier Card Click Handlers (Bi-directional sync)
    document.querySelectorAll('.flow-card').forEach(card => {
      card.addEventListener('click', () => {
        const tier = parseInt(card.getAttribute('data-tier'), 10);
        toggleTierHighlight(tier, card);
      });
    });
  }

  function setupN8nSection() {
    // Tab switching
    document.querySelectorAll('.n8n-tab').forEach(tabBtn => {
      tabBtn.addEventListener('click', () => {
        document.querySelectorAll('.n8n-tab').forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.n8n-tab-panel').forEach(p => p.classList.remove('active'));

        tabBtn.classList.add('active');
        const targetId = tabBtn.getAttribute('data-tab');
        const panel = document.getElementById(targetId);
        if (panel) panel.classList.add('active');
      });
    });

    // Refresh button
    if (elBtnFetchN8n) {
      elBtnFetchN8n.addEventListener('click', () => fetchLatestN8nExecution(false));
    }

    // Project to Timeline button
    if (elBtnProjectToTimeline) {
      elBtnProjectToTimeline.addEventListener('click', projectLatestN8nToDashboard);
    }

    // Copy buttons
    if (elBtnCopyRequest) {
      elBtnCopyRequest.addEventListener('click', () => copyToClipboard(elN8nRequestCode.textContent, elBtnCopyRequest));
    }
    if (elBtnCopyResponse) {
      elBtnCopyResponse.addEventListener('click', () => copyToClipboard(elN8nResponseCode.textContent, elBtnCopyResponse));
    }

    // Auto-sync toggle (3 seconds interval)
    if (elChkAutoSync) {
      elChkAutoSync.addEventListener('change', () => {
        toggleAutoSync(elChkAutoSync.checked);
      });
      toggleAutoSync(elChkAutoSync.checked);
    }
  }

  function toggleAutoSync(enable) {
    if (AppState.autoSyncTimer) {
      clearInterval(AppState.autoSyncTimer);
      AppState.autoSyncTimer = null;
    }
    if (enable) {
      AppState.autoSyncTimer = setInterval(() => {
        fetchLatestN8nExecution(true);
      }, 3000);
    }
  }

  function copyToClipboard(text, btnEl) {
    navigator.clipboard.writeText(text).then(() => {
      const originalText = btnEl.textContent;
      btnEl.textContent = '✅ Đã Copy!';
      setTimeout(() => { btnEl.textContent = originalText; }, 1800);
    });
  }

  async function loadPresets() {
    try {
      const resp = await fetch(API_PRESETS_URL);
      if (resp.ok) {
        AppState.presets = await resp.json();
        const firstKey = elPresetSelect.value || Object.keys(AppState.presets)[0];
        if (AppState.presets[firstKey]) {
          AppState.currentPayload = JSON.parse(JSON.stringify(AppState.presets[firstKey].payload));
        }
      }
    } catch (e) {
      console.warn('Could not load remote presets, using default fallback', e);
    }
  }

  async function triggerOptimization() {
    if (!AppState.currentPayload) return;

    elBtnOptimize.classList.add('loading');
    elEngineStatusText.textContent = 'OPTIMIZING...';
    elEngineStatusText.style.color = 'var(--amber)';

    const startTime = performance.now();

    try {
      const resp = await fetch(API_SCHEDULE_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(AppState.currentPayload)
      });

      const elapsed = Math.round(performance.now() - startTime);
      elExecutionTime.textContent = `• ${elapsed}ms`;

      if (!resp.ok) {
        throw new Error(`Server returned status ${resp.status}`);
      }

      const data = await resp.json();
      AppState.currentResponse = data;

      elEngineStatusText.textContent = 'OPTIMIZED 200 OK';
      elEngineStatusText.style.color = 'var(--emerald)';

      // Render Visualizations
      renderGanttTimeline(data, AppState.currentPayload);
      renderPipelineFlowMetrics(data);
      renderScoreBreakdown(data.scoreBreakdown);
      renderXAIReport(data.xaiReport);

    } catch (err) {
      console.error('Optimization failed:', err);
      elEngineStatusText.textContent = 'ERROR';
      elEngineStatusText.style.color = 'var(--rose)';
    } finally {
      elBtnOptimize.classList.remove('loading');
    }
  }

  // --- N8N EXECUTION INSPECTOR ---
  async function fetchLatestN8nExecution(silent = false) {
    try {
      const resp = await fetch(API_LATEST_EXEC_URL);
      if (!resp.ok) return;

      const resJson = await resp.json();
      if (resJson.status !== 'ok' || !resJson.data) {
        if (!silent) {
          elN8nStatusBadge.textContent = 'Chưa có request từ n8n';
          elN8nStatusBadge.style.color = 'var(--text-dim)';
        }
        return;
      }

      const exec = resJson.data;
      const isNew = !AppState.latestN8nExecution || AppState.latestN8nExecution.timestamp !== exec.timestamp;
      AppState.latestN8nExecution = exec;

      // Update Header & Meta
      elN8nStatusBadge.textContent = `Đã nhận lúc ${exec.timestamp.split(' ')[1] || exec.timestamp}`;
      elN8nStatusBadge.style.background = 'rgba(16, 185, 129, 0.2)';
      elN8nStatusBadge.style.color = '#34d399';

      elN8nTime.textContent = exec.timestamp;
      elN8nClientIp.textContent = `${exec.client_ip} (n8n/client)`;
      elN8nElapsed.textContent = `${Math.round(exec.elapsed_seconds * 1000)}ms`;

      const reqTasks = (exec.request && exec.request.tasks) || [];
      const resSessions = (exec.response && exec.response.sessions) || [];
      elN8nTaskCount.textContent = `${reqTasks.length} tasks`;
      elN8nSessionCount.textContent = `${resSessions.length} sessions`;

      // Tab 1: Request JSON
      elN8nRequestCode.textContent = JSON.stringify(exec.request, null, 2);

      // Tab 2: 12-Step Trace Cards
      render12StepTrace(exec);

      // Tab 3: Response JSON
      elN8nResponseCode.textContent = JSON.stringify(exec.response, null, 2);

      // Flash feedback if new
      if (isNew && !silent) {
        elN8nStatusBadge.style.boxShadow = '0 0 16px var(--emerald)';
        setTimeout(() => { elN8nStatusBadge.style.boxShadow = 'none'; }, 1500);
      }

    } catch (err) {
      if (!silent) console.error('Fetch latest execution failed:', err);
    }
  }

  function render12StepTrace(exec) {
    if (!elN8nTraceGrid) return;
    elN8nTraceGrid.innerHTML = '';

    const trace = (exec.response && exec.response.pipelineTrace) || {};
    const req = exec.request || {};
    const buckets = trace.strategyBuckets || {};

    const steps = [
      {
        title: 'Tầng 1 (B1-3): Quy Hoạch & Free Slots',
        icon: '🛡️',
        desc: `Phát hiện <b>${trace.freeSlotsCount || 0} slot trống</b> (Tổng: <b>${((trace.totalFreeMinutes || 0) / 60).toFixed(1)} giờ</b>) sau khi trừ <b>${(req.fixedEvents || []).length} sự kiện cố định</b>.`
      },
      {
        title: 'Tầng 2 (B4-6): Urgency & Buckets',
        icon: '⚡',
        desc: `Phân loại task: <b>${(buckets.critical || []).length} Critical</b>, <b>${(buckets.competition || []).length} Competition</b>, <b>${(buckets.normal || []).length} Normal</b> dựa trên Slack time và Starvation aging.`
      },
      {
        title: 'Tầng 3 (B7-8): Chunking & Ứng Viên',
        icon: '🧩',
        desc: `Sinh ra <b>${trace.candidatesEvaluatedCount || 1} kịch bản hoán vị</b> (Interleaved vs Batching). Áp dụng chunk kích thước 30m / 45m / 60m / 90m / 120m.`
      },
      {
        title: 'Tầng 4 (B9-11): Objective J & Tối Ưu',
        icon: '🎯',
        desc: `Điểm ban đầu: <b>${(trace.initialScore || 0).toFixed(1)}</b>. Áp dụng <b>${trace.repairsApplied || 0} sửa lỗi Repair</b> và 2-Opt local search đạt điểm <b>${(trace.finalScore || 0).toFixed(1)}</b>.`
      },
      {
        title: 'Tầng 5 (B12): Chốt Lịch & XAI',
        icon: '📊',
        desc: `Hành động: <b>${trace.stabilityAction || 'COMMITTED'}</b> (Cải thiện: <b>${(trace.stabilityImprovementRate || 0).toFixed(1)}%</b>). Tạo thành công văn bản giải trình lý do xếp lịch.`
      }
    ];

    steps.forEach(st => {
      const card = document.createElement('div');
      card.className = 'trace-card';
      card.innerHTML = `
        <div class="trace-card-title">${st.icon} ${st.title}</div>
        <div class="trace-card-content">${st.desc}</div>
      `;
      elN8nTraceGrid.appendChild(card);
    });
  }

  function projectLatestN8nToDashboard() {
    if (!AppState.latestN8nExecution) {
      alert('Chưa có dữ liệu n8n nào để chiếu lên Timeline!');
      return;
    }

    const exec = AppState.latestN8nExecution;
    AppState.currentPayload = exec.request;
    AppState.currentResponse = exec.response;

    // Render onto Gantt Timeline and Pipeline Flow
    renderGanttTimeline(exec.response, exec.request);
    renderPipelineFlowMetrics(exec.response);
    renderScoreBreakdown(exec.response.scoreBreakdown);
    renderXAIReport(exec.response.xaiReport);

    // Scroll to Top Timeline smoothly
    window.scrollTo({ top: 0, behavior: 'smooth' });

    // Flash Horizon badge to notify user
    elHorizonBadge.style.background = 'rgba(16, 185, 129, 0.3)';
    elHorizonBadge.style.color = '#34d399';
    elHorizonBadge.textContent = `Lịch thực tế từ n8n (${exec.timestamp})`;
    setTimeout(() => {
      elHorizonBadge.style.background = 'rgba(99, 102, 241, 0.2)';
      elHorizonBadge.style.color = '#a5b4fc';
    }, 2500);
  }

  // --- 1. RENDER GANTT TIMELINE ---
  function renderGanttTimeline(response, requestPayload) {
    elTimelineRuler.innerHTML = '';
    elTimelineTrack.innerHTML = '';

    // Determine Timeline Range (08:00 to 20:00 standard, or dynamically fit)
    const baseDateStr = (requestPayload.current_time || new Date().toISOString()).split('T')[0];
    const horizonStart = new Date(`${baseDateStr}T08:00:00`);
    const horizonEnd = new Date(`${baseDateStr}T20:00:00`);
    const totalMinutes = (horizonEnd - horizonStart) / 60000;

    elHorizonBadge.textContent = `Horizon: 08:00 - 20:00 (${(totalMinutes/60).toFixed(0)}h)`;

    // 1.1 Render Ruler Ticks (Every 1 hour)
    const totalHours = Math.round(totalMinutes / 60);
    for (let i = 0; i <= totalHours; i++) {
      const tickMinutes = i * 60;
      const tickPct = (tickMinutes / totalMinutes) * 100;
      const tickTime = new Date(horizonStart.getTime() + tickMinutes * 60000);
      const hoursStr = String(tickTime.getHours()).padStart(2, '0') + ':00';

      const tick = document.createElement('div');
      tick.className = 'ruler-tick';
      tick.style.left = `${tickPct}%`;
      tick.textContent = hoursStr;
      elTimelineRuler.appendChild(tick);
    }

    // 1.2 Render Now Indicator
    const nowTime = new Date(requestPayload.current_time || new Date());
    if (nowTime >= horizonStart && nowTime <= horizonEnd) {
      const nowMinutes = (nowTime - horizonStart) / 60000;
      const nowPct = (nowMinutes / totalMinutes) * 100;
      const nowLine = document.createElement('div');
      nowLine.className = 'now-indicator';
      nowLine.style.left = `${nowPct}%`;
      elTimelineTrack.appendChild(nowLine);

      // 1.3 Render Frozen Zone
      const frozenHours = (requestPayload.userPreferences && requestPayload.userPreferences.frozenZoneHours) || 2;
      const frozenEnd = new Date(nowTime.getTime() + frozenHours * 3600000);
      const frozenMinutes = (frozenEnd - horizonStart) / 60000;
      const frozenEndPct = Math.min(100, (frozenMinutes / totalMinutes) * 100);
      const frozenWidthPct = Math.max(0, frozenEndPct - nowPct);

      if (frozenWidthPct > 0) {
        const frozenOverlay = document.createElement('div');
        frozenOverlay.className = 'frozen-zone-overlay';
        frozenOverlay.style.left = `${nowPct}%`;
        frozenOverlay.style.width = `${frozenWidthPct}%`;
        frozenOverlay.innerHTML = `<span class="frozen-label">🔒 Đóng băng ${frozenHours}h</span>`;
        elTimelineTrack.appendChild(frozenOverlay);
      }
    }

    // 1.4 Render Fixed Events (Meetings)
    if (requestPayload.fixedEvents) {
      requestPayload.fixedEvents.forEach(fe => {
        const sTime = new Date(fe.startTime);
        const eTime = new Date(fe.endTime);
        if (sTime < horizonEnd && eTime > horizonStart) {
          const sMin = Math.max(0, (sTime - horizonStart) / 60000);
          const eMin = Math.min(totalMinutes, (eTime - horizonStart) / 60000);
          const leftPct = (sMin / totalMinutes) * 100;
          const widthPct = ((eMin - sMin) / totalMinutes) * 100;

          const block = document.createElement('div');
          block.className = 'fixed-event-block';
          block.style.left = `${leftPct}%`;
          block.style.width = `${widthPct}%`;
          block.textContent = `📅 ${fe.name}`;
          setupTooltip(block, `<b>Sự kiện cố định:</b> ${fe.name}<br>Thời gian: ${formatTime(sTime)} - ${formatTime(eTime)}`);
          elTimelineTrack.appendChild(block);
        }
      });
    }

    // 1.5 Render Scheduled Sessions
    const taskColorMap = {};
    let colorIdx = 0;

    if (response.sessions && response.sessions.length > 0) {
      response.sessions.forEach(sess => {
        const sTime = new Date(sess.startTime);
        const eTime = new Date(sess.endTime);

        if (!taskColorMap[sess.taskId]) {
          taskColorMap[sess.taskId] = TASK_COLORS[colorIdx % TASK_COLORS.length];
          colorIdx++;
        }
        const color = taskColorMap[sess.taskId];

        const sMin = Math.max(0, (sTime - horizonStart) / 60000);
        const eMin = Math.min(totalMinutes, (eTime - horizonStart) / 60000);
        const leftPct = (sMin / totalMinutes) * 100;
        const widthPct = ((eMin - sMin) / totalMinutes) * 100;

        const block = document.createElement('div');
        block.className = 'session-block';
        block.id = `sess_${sess.sessionId || sess.taskId}`;
        block.dataset.taskId = sess.taskId;
        block.dataset.duration = sess.duration || 60;
        block.style.left = `${leftPct}%`;
        block.style.width = `${widthPct}%`;
        block.style.background = color.bg;
        block.style.border = `1px solid ${color.border}`;

        const taskName = sess.taskName || sess.taskId;
        const durationMin = sess.duration || Math.round((eTime - sTime) / 60000);
        const energyIcon = sess.energyLevel === 'high' ? '⚡ High' : (sess.energyLevel === 'medium' ? '⚡ Med' : '⚡ Low');
        const frozenBadge = sess.isFrozen ? '🔒' : '';

        block.innerHTML = `
          <div class="session-title">${taskName} ${frozenBadge}</div>
          <div class="session-meta">
            <span>${formatTime(sTime)}-${formatTime(eTime)}</span>
            <span>• ${durationMin}m</span>
          </div>
        `;

        // Tooltip
        setupTooltip(block, `
          <b>${taskName}</b><br>
          Khung giờ: <b>${formatTime(sTime)} - ${formatTime(eTime)}</b> (${durationMin} phút)<br>
          Mức năng lượng: <b>${energyIcon}</b><br>
          Trạng thái: <b>${sess.isFrozen ? 'Đang đóng băng' : 'Tối ưu linh hoạt'}</b>
        `);

        // Click to trigger Bi-directional Sync
        block.addEventListener('click', (e) => {
          e.stopPropagation();
          selectSession(sess.sessionId || sess.taskId, sess.taskId);
        });

        elTimelineTrack.appendChild(block);
      });
    }
  }

  // --- 2. PIPELINE FLOW METRICS (5 TIERS) ---
  function renderPipelineFlowMetrics(response) {
    const trace = response.pipelineTrace || {};
    const buckets = trace.strategyBuckets || {};

    // Tier 1
    if (elMetricsT1) {
      elMetricsT1.innerHTML = `
        <span>• Free Slots: <b>${trace.freeSlotsCount || 0} slots</b></span>
        <span>• Tổng giờ trống: <b>${((trace.totalFreeMinutes || 0) / 60).toFixed(1)}h</b></span>
      `;
    }

    // Tier 2
    if (elMetricsT2) {
      const critCount = (buckets.critical || []).length;
      const compCount = (buckets.competition || []).length;
      const normCount = (buckets.normal || []).length;
      elMetricsT2.innerHTML = `
        <span>• Critical: <b>${critCount} task</b></span>
        <span>• Competition: <b>${compCount} task</b></span>
        <span>• Normal: <b>${normCount} task</b></span>
      `;
    }

    // Tier 3
    if (elMetricsT3) {
      elMetricsT3.innerHTML = `
        <span>• Ứng viên sinh ra: <b>${trace.candidatesEvaluatedCount || 1} kịch bản</b></span>
        <span>• Chunking: <b>30/45/60/90/120m</b></span>
      `;
    }

    // Tier 4
    if (elMetricsT4) {
      elMetricsT4.innerHTML = `
        <span>• Repair sửa lỗi: <b>${trace.repairsApplied || 0} lần</b></span>
        <span>• 2-Opt cải thiện: <b>${trace.localSearchSwaps ? 'Có (+Swap)' : '0 (Tối ưu)'}</b></span>
      `;
    }

    // Tier 5
    if (elMetricsT5) {
      elMetricsT5.innerHTML = `
        <span>• Trạng thái: <b>${trace.stabilityAction || 'COMMITTED'}</b></span>
        <span>• Điểm J toàn cục: <b>${(trace.finalScore || response.score || 0).toFixed(1)}</b></span>
      `;
    }
  }

  // --- 3. SCORE BREAKDOWN RENDERER ---
  function renderScoreBreakdown(scoreObj) {
    if (!scoreObj) return;

    if (elValEnergy) elValEnergy.textContent = `+${(scoreObj.energyBonus || 0).toFixed(1)}`;
    if (elValPref) elValPref.textContent = `+${(scoreObj.preferenceBonus || 0).toFixed(1)}`;
    if (elValSwitch) elValSwitch.textContent = `-${(scoreObj.switchingPenalty || 0).toFixed(1)}`;
    if (elValFrag) elValFrag.textContent = `-${(scoreObj.fragmentationPenalty || 0).toFixed(1)}`;
    if (elValTardiness) elValTardiness.textContent = `-${(scoreObj.tardinessPenalty || 0).toFixed(1)}`;

    const total = scoreObj.finalScore || 0;
    if (elValTotal) {
      elValTotal.textContent = `${total >= 0 ? '+' : ''}${total.toFixed(1)}`;
      elValTotal.style.color = total >= 0 ? 'var(--emerald)' : 'var(--amber)';
    }
  }

  // --- 4. XAI REPORT RENDERER ---
  function renderXAIReport(xai) {
    if (!elXaiList) return;
    elXaiList.innerHTML = '';

    if (!xai || !xai.taskExplanations || xai.taskExplanations.length === 0) {
      elXaiList.innerHTML = `
        <div class="xai-item">
          <div class="task-name">Lịch trình tối ưu đã sẵn sàng</div>
          <div>Không có xung đột hay cảnh báo trễ hạn nào trong chu kỳ này.</div>
        </div>
      `;
      return;
    }

    xai.taskExplanations.forEach(item => {
      const xaiItem = document.createElement('div');
      xaiItem.className = 'xai-item';
      xaiItem.dataset.taskId = item.taskId;

      const reasons = (item.reasons || []).join(' • ') || 'Đã phân bổ vào khung giờ phù hợp nhất.';
      const warnings = (item.warnings || []).map(w => `<span style="color: var(--amber);">⚠️ ${w}</span>`).join('<br>');

      xaiItem.innerHTML = `
        <div class="task-name">${item.taskName}</div>
        <div style="color: var(--text-muted); font-size: 0.78rem;">${reasons}</div>
        ${warnings ? `<div style="margin-top: 4px; font-size: 0.75rem;">${warnings}</div>` : ''}
      `;

      elXaiList.appendChild(xaiItem);
    });
  }

  // --- 5. BI-DIRECTIONAL SYNCHRONIZATION ---
  function selectSession(sessionId, taskId) {
    AppState.selectedSessionId = sessionId;

    // Highlight session block on timeline
    document.querySelectorAll('.session-block').forEach(b => {
      if (b.dataset.taskId === taskId) {
        b.classList.add('is-highlighted');
        b.classList.remove('is-dimmed');
      } else {
        b.classList.remove('is-highlighted');
        b.classList.add('is-dimmed');
      }
    });

    // Highlight corresponding XAI card
    document.querySelectorAll('.xai-item').forEach(xi => {
      if (xi.dataset.taskId === taskId) {
        xi.style.borderColor = 'var(--emerald)';
        xi.style.background = 'rgba(16, 185, 129, 0.15)';
        xi.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      } else {
        xi.style.borderColor = 'var(--border-subtle)';
        xi.style.background = 'rgba(10, 15, 29, 0.6)';
      }
    });
  }

  function toggleTierHighlight(tier, cardEl) {
    const isAlreadyActive = cardEl.classList.contains('active');

    // Clear all card states
    document.querySelectorAll('.flow-card').forEach(c => c.classList.remove('active'));
    document.querySelectorAll('.session-block').forEach(b => {
      b.classList.remove('is-highlighted', 'is-dimmed');
    });

    if (isAlreadyActive) {
      AppState.activeTierHighlight = null;
      return;
    }

    cardEl.classList.add('active');
    AppState.activeTierHighlight = tier;

    // Action per Tier
    if (tier === 1) {
      // Dim sessions, highlight free space
      document.querySelectorAll('.session-block').forEach(b => b.classList.add('is-dimmed'));
    } else if (tier === 2) {
      // Highlight high-priority sessions
      document.querySelectorAll('.session-block').forEach(b => {
        b.classList.remove('is-dimmed');
      });
    } else if (tier === 4) {
      // Highlight repair actions
      document.querySelectorAll('.session-block').forEach(b => {
        if (b.id && b.id.includes('repair')) {
          b.classList.add('is-highlighted');
        }
      });
    }
  }

  // --- Helpers ---
  function formatTime(dt) {
    return `${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`;
  }

  function setupTooltip(element, htmlContent) {
    element.addEventListener('mouseenter', (e) => {
      elTooltip.innerHTML = htmlContent;
      elTooltip.style.display = 'block';
      moveTooltip(e);
    });
    element.addEventListener('mousemove', moveTooltip);
    element.addEventListener('mouseleave', () => {
      elTooltip.style.display = 'none';
    });
  }

  function moveTooltip(e) {
    const offset = 15;
    let x = e.clientX + offset;
    let y = e.clientY + offset;
    if (x + 300 > window.innerWidth) x = e.clientX - 310;
    if (y + 120 > window.innerHeight) y = e.clientY - 120;
    elTooltip.style.left = `${x}px`;
    elTooltip.style.top = `${y}px`;
  }

})();
