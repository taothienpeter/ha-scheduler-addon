// Smart Calendar Scheduler - Dashboard Application Logic
// Supports Home Assistant Ingress and Direct Port Access

(function() {
  'use strict';

  // Base Path Resolver for Home Assistant Ingress
  const BASE_PATH = window.location.pathname.replace(/\/$/, '');
  const API_PRESETS_URL = `${BASE_PATH}/api/presets`;
  const API_SCHEDULE_URL = `${BASE_PATH}/api/schedule`;

  // Central Application State
  const AppState = {
    presets: {},
    currentPayload: null,
    currentResponse: null,
    activeTierHighlight: null,
    selectedSessionId: null
  };

  // Color Palettes for Task Sessions
  const TASK_COLORS = [
    { bg: 'linear-gradient(135deg, #6366f1, #4f46e5)', border: '#818cf8' },
    { bg: 'linear-gradient(135deg, #06b6d4, #0891b2)', border: '#22d3ee' },
    { bg: 'linear-gradient(135deg, #8b5cf6, #7c3aed)', border: '#a78bfa' },
    { bg: 'linear-gradient(135deg, #10b981, #059669)', border: '#34d399' },
    { bg: 'linear-gradient(135deg, #f59e0b, #d97706)', border: '#fbbf24' }
  ];

  // DOM Elements
  const elPresetSelect = document.getElementById('presetSelect');
  const elBtnOptimize = document.getElementById('btnOptimize');
  const elEngineStatusText = document.getElementById('engineStatusText');
  const elExecutionTime = document.getElementById('executionTime');
  const elHorizonBadge = document.getElementById('horizonBadge');
  const elTimelineRuler = document.getElementById('timelineRuler');
  const elTimelineTrack = document.getElementById('timelineTrack');
  const elXaiList = document.getElementById('xaiList');
  const elTooltip = document.getElementById('dashboardTooltip');

  // Score Table Elements
  const elValEnergy = document.getElementById('valEnergyBonus');
  const elValPref = document.getElementById('valPrefBonus');
  const elValSwitch = document.getElementById('valSwitchPenalty');
  const elValFrag = document.getElementById('valFragPenalty');
  const elValTardiness = document.getElementById('valTardinessPenalty');
  const elValTotal = document.getElementById('valTotalScore');

  // Metrics Badges
  const elMetricsT1 = document.getElementById('metricsTier1');
  const elMetricsT2 = document.getElementById('metricsTier2');
  const elMetricsT3 = document.getElementById('metricsTier3');
  const elMetricsT4 = document.getElementById('metricsTier4');
  const elMetricsT5 = document.getElementById('metricsTier5');

  // Init
  window.addEventListener('DOMContentLoaded', initApp);

  async function initApp() {
    setupEventListeners();
    await loadPresets();
    triggerOptimization();
  }

  function setupEventListeners() {
    elPresetSelect.addEventListener('change', () => {
      const selectedKey = elPresetSelect.value;
      if (AppState.presets[selectedKey]) {
        AppState.currentPayload = JSON.parse(JSON.stringify(AppState.presets[selectedKey].payload));
        triggerOptimization();
      }
    });

    elBtnOptimize.addEventListener('click', triggerOptimization);

    // Flow Tier Card Click Handlers (Bi-directional sync)
    document.querySelectorAll('.flow-card').forEach(card => {
      card.addEventListener('click', () => {
        const tier = parseInt(card.getAttribute('data-tier'), 10);
        toggleTierHighlight(tier, card);
      });
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

    // 1.4 Render Free Slots
    // Approximate free slots by inspecting gaps or pipeline free slots
    if (response.pipelineTrace && response.pipelineTrace.freeSlotsCount > 0) {
      // Create visual slot representations
      renderFreeSlotsLayer(horizonStart, totalMinutes);
    }

    // 1.5 Render Fixed Events (Meetings)
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

    // 1.6 Render Scheduled Sessions
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

  function renderFreeSlotsLayer(horizonStart, totalMinutes) {
    // Generate soft background slots where no fixed events exist
    // Visual aid for Free Slots
  }

  // --- 2. PIPELINE FLOW METRICS (5 TIERS) ---
  function renderPipelineFlowMetrics(response) {
    const trace = response.pipelineTrace || {};
    const buckets = trace.strategyBuckets || {};

    // Tier 1
    elMetricsT1.innerHTML = `
      <span>• Free Slots: <b>${trace.freeSlotsCount || 0} slots</b></span>
      <span>• Tổng giờ trống: <b>${((trace.totalFreeMinutes || 0) / 60).toFixed(1)}h</b></span>
    `;

    // Tier 2
    const critCount = (buckets.critical || []).length;
    const compCount = (buckets.competition || []).length;
    const normCount = (buckets.normal || []).length;
    elMetricsT2.innerHTML = `
      <span>• Critical: <b>${critCount} task</b></span>
      <span>• Competition: <b>${compCount} task</b></span>
      <span>• Normal: <b>${normCount} task</b></span>
    `;

    // Tier 3
    elMetricsT3.innerHTML = `
      <span>• Ứng viên sinh ra: <b>${trace.candidatesEvaluatedCount || 1} kịch bản</b></span>
      <span>• Chunking: <b>30/45/60/90/120m</b></span>
    `;

    // Tier 4
    elMetricsT4.innerHTML = `
      <span>• Repair sửa lỗi: <b>${trace.repairsApplied || 0} lần</b></span>
      <span>• 2-Opt cải thiện: <b>${trace.localSearchSwaps ? 'Có (+Swap)' : '0 (Tối ưu)'}</b></span>
    `;

    // Tier 5
    elMetricsT5.innerHTML = `
      <span>• Trạng thái: <b>${trace.stabilityAction || 'COMMITTED'}</b></span>
      <span>• Điểm J toàn cục: <b>${(trace.finalScore || response.score || 0).toFixed(1)}</b></span>
    `;
  }

  // --- 3. SCORE BREAKDOWN RENDERER ---
  function renderScoreBreakdown(scoreObj) {
    if (!scoreObj) return;

    elValEnergy.textContent = `+${(scoreObj.energyBonus || 0).toFixed(1)}`;
    elValPref.textContent = `+${(scoreObj.preferenceBonus || 0).toFixed(1)}`;
    elValSwitch.textContent = `-${(scoreObj.switchingPenalty || 0).toFixed(1)}`;
    elValFrag.textContent = `-${(scoreObj.fragmentationPenalty || 0).toFixed(1)}`;
    elValTardiness.textContent = `-${(scoreObj.tardinessPenalty || 0).toFixed(1)}`;

    const total = scoreObj.finalScore || 0;
    elValTotal.textContent = `${total >= 0 ? '+' : ''}${total.toFixed(1)}`;
    elValTotal.style.color = total >= 0 ? 'var(--emerald)' : 'var(--amber)';
  }

  // --- 4. XAI REPORT RENDERER ---
  function renderXAIReport(xai) {
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
