/**
 * app.js — Frontend Logic for OBOR
 * Handles map rendering, SSE data stream, UI updates, and animations.
 */

// ─── Global State ───────────────────────────────────────────────────────────
let map;
let fireMarkers = new Map();
let currentStats = { activeFires: 0, totalAcres: 0, vi: 0 };
let eventSource = null;
let reconnectDelay = 1000;

// ─── DOM Elements ───────────────────────────────────────────────────────────
const els = {
    statFires:    document.getElementById('stat-active-fires'),
    statAcres:    document.getElementById('stat-total-acres'),
    statVI:       document.getElementById('stat-vi'),
    statTTV:      document.getElementById('stat-ttv'),
    firesTable:   document.getElementById('fires-table-body'),
    viGaugePath:  document.getElementById('vi-gauge-path'),
    viGaugeText:  document.getElementById('vi-gauge-text'),
    valC1:        document.getElementById('val-c1'),
    valC2:        document.getElementById('val-c2'),
    valC3:        document.getElementById('val-c3'),
    barC1:        document.getElementById('bar-c1'),
    barC2:        document.getElementById('bar-c2'),
    barC3:        document.getElementById('bar-c3'),
    predictions:  document.getElementById('predictions-panel'),
    feed:         document.getElementById('activity-feed'),
    dispatch:     document.getElementById('dispatch-log'),
    connDot:      document.getElementById('connection-dot'),
    connStatus:   document.getElementById('connection-status'),
    predictionTable: document.getElementById('prediction-table-body'),
    btnTogglePred:   document.getElementById('btn-toggle-pred'),
    // Jev AI Supervisor elements
    jevStatusBadge:   document.getElementById('jev-status-badge'),
    jevThreatVal:     document.getElementById('jev-threat-val'),
    jevThreatBar:     document.getElementById('jev-threat-bar'),
    jevDispatchVal:   document.getElementById('jev-dispatch-val'),
    jevDispatchBar:   document.getElementById('jev-dispatch-bar'),
    jevOverrideVal:   document.getElementById('jev-override-val'),
    jevOverrideBar:   document.getElementById('jev-override-bar'),
    jevResponseLevel: document.getElementById('jev-response-level'),
    jevResponseConf:  document.getElementById('jev-response-conf'),
    jevSeverityScore: document.getElementById('jev-severity-score'),
    jevSeverityConf:  document.getElementById('jev-severity-conf'),
    jevLatency:       document.getElementById('jev-latency'),
    jevOverrideStatus:document.getElementById('jev-override-status'),
};

// ─── Utilities ──────────────────────────────────────────────────────────────
const formatNumber = (num) => new Intl.NumberFormat().format(Math.round(num));

const timeAgo = (ts) => {
    const now = Date.now();
    // Handle both epoch seconds and ISO strings
    const then = typeof ts === 'number'
        ? (ts > 1e12 ? ts : ts * 1000)  // epoch seconds → ms
        : new Date(ts).getTime();
    const diffSec = (now - then) / 1000;
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
};

const interpolateColor = (val) => {
    // val ∈ [-1, +1] → Red(-1) → Yellow(0) → Green(+1)
    const t = (val + 1) / 2; // normalize to 0..1
    if (t < 0.5) {
        const p = t / 0.5;
        return `rgb(255, ${Math.round(59 + p * 107)}, ${Math.round(59 * (1 - p) + 35 * p)})`;
    } else {
        const p = (t - 0.5) / 0.5;
        return `rgb(${Math.round(245 - p * 245)}, ${Math.round(166 + p * 51)}, ${Math.round(35 + p * 91)})`;
    }
};

const animateValue = (el, start, end, duration) => {
    const isFloat = !Number.isInteger(end) && Math.abs(end) < 100;
    let startTime = null;
    const step = (ts) => {
        if (!startTime) startTime = ts;
        const progress = Math.min((ts - startTime) / duration, 1);
        const current = start + progress * (end - start);
        el.textContent = isFloat ? current.toFixed(2) : formatNumber(current);
        if (progress < 1) requestAnimationFrame(step);
    };
    requestAnimationFrame(step);
};

// ─── Audio Alert (Web Audio API) ────────────────────────────────────────────
let audioCtx = null;
const playEmergencyAlert = () => {
    try {
        if (!audioCtx) audioCtx = new (window.AudioContext || window.webkitAudioContext)();
        if (audioCtx.state === 'suspended') audioCtx.resume();

        const osc = audioCtx.createOscillator();
        const gain = audioCtx.createGain();
        osc.type = 'square';
        osc.frequency.setValueAtTime(880, audioCtx.currentTime);
        osc.frequency.setValueAtTime(660, audioCtx.currentTime + 0.15);
        osc.frequency.setValueAtTime(880, audioCtx.currentTime + 0.3);
        gain.gain.setValueAtTime(0.08, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.5);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.5);
    } catch (e) {
        console.warn('Audio alert failed:', e);
    }
};

// ─── Map ────────────────────────────────────────────────────────────────────
// ─── Map & Layer Groups ─────────────────────────────────────────────────────
let fireLayerGroup;
let daopsLayerGroup;
let waterLayerGroup;
let predictionLayerGroup;
let darkCanvasLayer;
let darkLabelsLayer;
let satelliteLayer;

const initMap = () => {
    // Centered on Kalimantan / Borneo
    map = L.map('fire-map').setView([-1.5, 114.0], 6);

    // Free, reliable, keyless ESRI Dark Canvas + World Satellite
    darkCanvasLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a> &bull; OBOR Kalimantan',
        maxZoom: 16
    });

    darkLabelsLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}', {
        attribution: '',
        maxZoom: 16,
        pane: 'labels'
    });

    satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: '&copy; <a href="https://www.esri.com/">Esri</a> &bull; World Imagery',
        maxZoom: 19
    });

    // Create a special pane for labels so borders & names stay crisp above layers
    map.createPane('labels');
    map.getPane('labels').style.zIndex = 450;
    map.getPane('labels').style.pointerEvents = 'none';

    // Add dark canvas + reference labels by default
    darkCanvasLayer.addTo(map);
    darkLabelsLayer.addTo(map);

    fireLayerGroup = L.layerGroup().addTo(map);
    predictionLayerGroup = L.layerGroup().addTo(map);
    daopsLayerGroup = L.layerGroup().addTo(map);
    waterLayerGroup = L.layerGroup().addTo(map);

    loadDaopsHQs();
    loadWaterSources();
    loadPredictionsHeatmap();
    setupLayerToggles();
};

const loadDaopsHQs = async () => {
    try {
        const resp = await fetch('/api/warehouse/hqs');
        if (!resp.ok) return;
        const data = await resp.json();
        const hqs = data.hqs || [];

        hqs.forEach(hq => {
            const icon = L.divIcon({
                className: 'daops-marker-icon',
                html: '<span>🚒</span>',
                iconSize: [26, 26],
                iconAnchor: [13, 13]
            });
            const marker = L.marker([hq.lat, hq.lon], { icon });
            marker.bindPopup(`
                <div style="font-family:Inter,sans-serif;min-width:200px;">
                    <strong style="color:#38bdf8;font-size:13px;">${hq.name}</strong><br>
                    <span style="color:#aaa;">${hq.province || ''} &bull; ${hq.regency || ''}</span><br><br>
                    👨‍🚒 Crew on duty: <strong>${hq.crew || 10} firefighters</strong><br>
                    📻 Radio: <strong>${hq.radio || 'VHF 142.5 MHz'}</strong><br>
                    🏢 Agency: <strong>${hq.agency || 'MANGGALA AGNI'}</strong>
                </div>
            `);
            daopsLayerGroup.addLayer(marker);
        });
    } catch (e) {
        console.warn('Failed to load Daops HQs:', e);
    }
};

const loadWaterSources = async () => {
    try {
        const resp = await fetch('/api/warehouse/water-sources');
        if (!resp.ok) return;
        const data = await resp.json();
        const sources = data.water_sources || [];

        sources.forEach(w => {
            const icon = L.divIcon({
                className: 'water-marker-icon',
                html: '<span>💧</span>',
                iconSize: [24, 24],
                iconAnchor: [12, 12]
            });
            const marker = L.marker([w.lat, w.lon], { icon });
            marker.bindPopup(`
                <div style="font-family:Inter,sans-serif;min-width:190px;">
                    <strong style="color:#34d399;font-size:13px;">${w.name}</strong><br>
                    <span style="color:#aaa;">${w.province || ''}</span><br><br>
                    🌊 Type: <strong>${w.type}</strong><br>
                    📦 Capacity: <strong>${formatNumber(w.capacity_m3 || 0)} m³</strong><br>
                    ⚙️ Pump Accessible: <strong>Yes</strong>
                </div>
            `);
            waterLayerGroup.addLayer(marker);
        });
    } catch (e) {
        console.warn('Failed to load water sources:', e);
    }
};

const setupLayerToggles = () => {
    const btnFires = document.getElementById('btn-toggle-fires');
    const btnPred = document.getElementById('btn-toggle-pred');
    const btnDaops = document.getElementById('btn-toggle-daops');
    const btnWater = document.getElementById('btn-toggle-water');

    if (btnFires) {
        btnFires.addEventListener('click', () => {
            if (map.hasLayer(fireLayerGroup)) {
                map.removeLayer(fireLayerGroup);
                btnFires.classList.remove('active');
            } else {
                map.addLayer(fireLayerGroup);
                btnFires.classList.add('active');
            }
        });
    }

    if (btnPred) {
        btnPred.addEventListener('click', () => {
            if (map.hasLayer(predictionLayerGroup)) {
                map.removeLayer(predictionLayerGroup);
                btnPred.classList.remove('active');
            } else {
                map.addLayer(predictionLayerGroup);
                btnPred.classList.add('active');
            }
        });
    }

    if (btnDaops) {
        btnDaops.addEventListener('click', () => {
            if (map.hasLayer(daopsLayerGroup)) {
                map.removeLayer(daopsLayerGroup);
                btnDaops.classList.remove('active');
            } else {
                map.addLayer(daopsLayerGroup);
                btnDaops.classList.add('active');
            }
        });
    }

    if (btnWater) {
        btnWater.addEventListener('click', () => {
            if (map.hasLayer(waterLayerGroup)) {
                map.removeLayer(waterLayerGroup);
                btnWater.classList.remove('active');
            } else {
                map.addLayer(waterLayerGroup);
                btnWater.classList.add('active');
            }
        });
    }

    const btnSatellite = document.getElementById('btn-toggle-satellite');
    if (btnSatellite) {
        btnSatellite.addEventListener('click', () => {
            if (map.hasLayer(satelliteLayer)) {
                map.removeLayer(satelliteLayer);
                map.addLayer(darkCanvasLayer);
                btnSatellite.classList.remove('active');
            } else {
                map.removeLayer(darkCanvasLayer);
                map.addLayer(satelliteLayer);
                btnSatellite.classList.add('active');
            }
        });
    }
};

const loadPredictionsHeatmap = async () => {
    try {
        const resp = await fetch('/api/prediction/heatmap?limit=150');
        if (!resp.ok) return;
        const data = await resp.json();
        const features = data.features || [];

        predictionLayerGroup.clearLayers();

        features.forEach(feat => {
            const coords = feat.geometry.coordinates; // [lon, lat]
            const p = feat.properties;
            const riskPct = (p.calibrated_risk * 100).toFixed(1);
            
            let color = '#fde047'; // yellow WASPADA
            let radius = 7;
            if (p.risk_tier.includes('AWAS')) {
                color = '#ef4444';
                radius = 11;
            } else if (p.risk_tier.includes('SIAGA')) {
                color = '#f97316';
                radius = 9;
            }

            const marker = L.circleMarker([coords[1], coords[0]], {
                radius: radius,
                fillColor: color,
                color: '#ffffff',
                weight: 1.5,
                opacity: 0.9,
                fillOpacity: 0.75
            });

            marker.bindPopup(`
                <div style="font-family:Inter,sans-serif;min-width:220px;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;">
                        <strong style="color:${color};font-size:13px;">🔮 PREDIKSI RISIKO 24 JAM</strong>
                        <span style="font-size:10px;background:rgba(255,255,255,0.1);padding:2px 6px;border-radius:4px;">${p.grid_id}</span>
                    </div>
                    <span style="color:#aaa;font-size:11px;">📍 ${p.province || 'Kalimantan'}</span><br><br>
                    🔥 Tingkat Bahaya: <strong style="color:${color}">${p.risk_tier}</strong><br>
                    📊 Probabilitas Terkalibrasi: <strong>${riskPct}%</strong><br>
                    ⏱️ Estimasi Waktu (ETA): <strong style="color:#38bdf8;">${p.estimated_eta || '3-6 jam (Siang Ini)'}</strong><br>
                    ⚡ Estimasi Intensitas (FRP): <strong>${p.predicted_frp_mw} MW</strong><br>
                    ☀️ Hari Kering (CDD): <strong>${p.dry_days} hari</strong><br>
                    <hr style="border:none;border-top:1px solid rgba(255,255,255,0.1);margin:6px 0;">
                    <span style="font-size:10px;color:#888;">Model: XGBoost (Shallow) + LightGBM Regressor</span>
                </div>
            `);

            predictionLayerGroup.addLayer(marker);
        });
    } catch (e) {
        console.warn('Failed to load predictions heatmap:', e);
    }
};

const loadTopPredictionsTable = async () => {
    try {
        const resp = await fetch('/api/prediction/top-risk?limit=15');
        if (!resp.ok) return;
        const data = await resp.json();
        const cells = data.top_risk_cells || [];
        if (!els.predictionTable) return;

        if (cells.length === 0) {
            els.predictionTable.innerHTML = '<tr><td colspan="8" style="text-align:center;color:#888;">Tidak ada sel risiko tinggi yang terdeteksi saat ini.</td></tr>';
            return;
        }

        els.predictionTable.innerHTML = cells.map(c => {
            const riskPct = (c.calibrated_risk * 100).toFixed(1);
            let badgeClass = 'badge-waspada';
            if (c.risk_tier.includes('AWAS')) badgeClass = 'badge-awas';
            else if (c.risk_tier.includes('SIAGA')) badgeClass = 'badge-siaga';
            else if (c.risk_tier.includes('NORMAL')) badgeClass = 'badge-normal';

            return `
                <tr>
                    <td><strong>${c.grid_id}</strong></td>
                    <td>${c.province || 'Kalimantan'}</td>
                    <td><strong>${riskPct}%</strong> <span style="font-size:10px;color:#888;">(raw ${(c.raw_risk * 100).toFixed(0)}%)</span></td>
                    <td><span class="badge ${badgeClass}">${c.risk_tier}</span></td>
                    <td><span style="color:#38bdf8;font-weight:600;font-size:11px;">${c.estimated_eta || '⚡ 2-5 jam (13:00-16:30)'}</span></td>
                    <td><span style="color:#f5a623;font-weight:600;">${c.predicted_frp_mw} MW</span></td>
                    <td>${c.consecutive_dry_days} hari</td>
                    <td>${c.hotspot_count_prev_7d}</td>
                </tr>
            `;
        }).join('');
    } catch (e) {
        console.warn('Failed to load top predictions table:', e);
    }
};

const getAlertColor = (level) => ({
    'MONITOR': '#4dabf7',
    'WATCH': '#f5a623',
    'WARNING': '#ff6b35',
    'EMERGENCY': '#ff3b3b',
}[level] || '#8888a0');

const updateFireMarkers = (fires) => {
    const activeIds = new Set();

    fires.forEach(fire => {
        const id = fire.fire_id;
        activeIds.add(id);
        const lat = fire.latitude;
        const lon = fire.longitude;
        const acres = fire.daily_acres || 0;
        const ha = fire.hectares || Math.round(acres / 2.47105);
        const alert = fire.alert_level || 'MONITOR';
        const contained = fire.percent_contained || 0;
        const name = fire.name || 'Unknown';
        const isPeat = fire.is_peatland || false;
        const radius = Math.max(6, Math.min(Math.sqrt(ha) * 1.5, 36));
        const color = isPeat ? '#ff3b3b' : getAlertColor(alert);

        let weatherInfo = '';
        if (fire.weather) {
            weatherInfo = `<br>🌡️ ${fire.weather.temperature_c}°C &bull; 💧 ${fire.weather.humidity_pct}% &bull; 💨 ${fire.weather.wind_speed_kph} km/h`;
        }

        const popupContent = `
            <div style="font-family:Inter,sans-serif;min-width:210px;">
                <strong style="font-size:14px;">${name}</strong><br>
                <span style="color:#aaa;">${fire.province || fire.state || ''} &bull; ${fire.county || ''}</span><br>
                ${isPeat ? '<span class="peat-tag">🔥 Lahan Gambut (Peatland)</span>' : '<span class="mineral-tag">Mineral Forest</span>'}<br><br>
                📏 Area: <strong>${formatNumber(ha)} ha</strong> (${formatNumber(acres)} ac)<br>
                📊 Contained: <strong>${contained.toFixed(0)}%</strong><br>
                ⚠️ Alert: <strong style="color:${color}">${alert}</strong>
                ${weatherInfo}
            </div>
        `;

        if (fireMarkers.has(id)) {
            const marker = fireMarkers.get(id);
            marker.setLatLng([lat, lon]);
            marker.setRadius(radius);
            marker.setStyle({ color, fillColor: color, fillOpacity: isPeat ? 0.65 : 0.5, weight: 2 });
            marker.setPopupContent(popupContent);
        } else {
            const marker = L.circleMarker([lat, lon], {
                radius, color, fillColor: color, fillOpacity: isPeat ? 0.65 : 0.5, weight: 2
            }).addTo(fireLayerGroup);
            marker.bindPopup(popupContent);
            marker.on('click', () => map.flyTo([lat, lon], 8, { duration: 1.2 }));
            fireMarkers.set(id, marker);
        }
    });

    // Remove markers for fires no longer active
    for (const [id, marker] of fireMarkers) {
        if (!activeIds.has(id)) {
            fireLayerGroup.removeLayer(marker);
            fireMarkers.delete(id);
        }
    }
};

// ─── Fires Table ────────────────────────────────────────────────────────────
const renderFiresTable = (fires) => {
    const sorted = [...fires].sort((a, b) => (b.hectares || b.daily_acres || 0) - (a.hectares || a.daily_acres || 0));
    els.firesTable.innerHTML = '';

    sorted.forEach(fire => {
        const acres = fire.daily_acres || 0;
        const ha = fire.hectares || Math.round(acres / 2.47105);
        const contained = (fire.percent_contained || 0).toFixed(0);
        const alert = fire.alert_level || 'MONITOR';
        const isPeat = fire.is_peatland || false;
        const tr = document.createElement('tr');

        // Determine trend from acre_change if available, otherwise stable
        let trendHtml = '<span style="color:var(--text-secondary)">●</span>';
        if (fire.acre_change > 50) {
            trendHtml = '<span style="color:var(--danger)">▲</span>';
        } else if (fire.acre_change < -20) {
            trendHtml = '<span style="color:var(--success)">▼</span>';
        }

        tr.innerHTML = `
            <td><strong>${fire.name || 'Unknown'}</strong></td>
            <td>${fire.province || fire.state || '—'} / ${fire.county || '—'}</td>
            <td><strong>${formatNumber(ha)} ha</strong> <span style="color:#888;font-size:0.75rem;">(${formatNumber(acres)} ac)</span></td>
            <td>${contained}%</td>
            <td>${isPeat ? '<span class="peat-tag">Gambut</span>' : '<span class="mineral-tag">Mineral</span>'}</td>
            <td><span class="badge badge-${alert.toLowerCase()}">${alert}</span></td>
            <td>${trendHtml}</td>
        `;
        tr.style.cursor = 'pointer';
        tr.addEventListener('click', () => {
            if (fire.latitude && fire.longitude) {
                map.flyTo([fire.latitude, fire.longitude], 8, { duration: 1.2 });
            }
        });
        els.firesTable.appendChild(tr);
    });
};

// ─── VI Gauge ───────────────────────────────────────────────────────────────
const updateVIGauge = (vi) => {
    // SVG arc from -1 to +1, total arc length ≈ 251.3 (r=80 semicircle)
    const maxDash = 251.3;
    const normalized = Math.max(0, Math.min(1, (vi + 1) / 2));
    const dashLength = normalized * maxDash;
    els.viGaugePath.style.strokeDasharray = `${dashLength} ${maxDash}`;

    // Animate the text
    animateValue(els.viGaugeText, currentStats.vi, vi, 800);

    // Update stat card
    animateValue(els.statVI, currentStats.vi, vi, 800);
    currentStats.vi = vi;
};

const updateVIComponents = (c1, c2, c3) => {
    els.valC1.textContent = c1.toFixed(2);
    els.valC2.textContent = c2.toFixed(2);
    els.valC3.textContent = c3.toFixed(2);

    // Map [-1, +1] → [0%, 100%]
    els.barC1.style.width = `${((c1 + 1) / 2) * 100}%`;
    els.barC2.style.width = `${((c2 + 1) / 2) * 100}%`;
    els.barC3.style.width = `${((c3 + 1) / 2) * 100}%`;

    els.barC1.style.backgroundColor = interpolateColor(c1);
    els.barC2.style.backgroundColor = interpolateColor(c2);
    els.barC3.style.backgroundColor = interpolateColor(c3);
};

// ─── Feed Items ─────────────────────────────────────────────────────────────
const addFeedItem = (container, data, isDispatch = false, isInitial = false) => {
    const div = document.createElement('div');
    div.className = `feed-item ${isDispatch ? 'dispatch-item' : ''}`;

    if (isDispatch && !isInitial) {
        div.classList.add('shake-anim');
        playEmergencyAlert();
    }

    const message = data.message || data.fire_name || JSON.stringify(data);
    const timestamp = data.timestamp || Date.now() / 1000;

    let extraInfo = '';
    if (isDispatch) {
        const severity = data.severity || 'CRITICAL';
        const personnel = data.total_personnel || '';
        const eta = data.response_time_min || data.estimated_response_time_min || '';
        const evac = data.evacuation || data.evacuation_advisory;
        const station = data.station || data.nearest_station || '';
        let resourcesList = data.resources || [];
        if (data.resources_deployed && (!resourcesList || resourcesList.length === 0)) {
            resourcesList = data.resources_deployed.map(r => r.display || `${r.icon || '🚒'} ${r.name || 'Resource'}`);
        }

        extraInfo = `
            <div style="margin-top:0.4rem;font-size:0.8rem;color:var(--text-secondary);">
                ${severity ? '⚡ ' + severity : ''}
                ${personnel ? ' · 👥 ' + personnel + ' personel' : ''}
                ${eta ? ' · ⏱️ ETA ' + eta + 'min' : ''}
                ${evac ? ' · 🚨 EVAKUASI' : ''}
                ${station ? '<br>🏢 ' + station : ''}
            </div>
            ${resourcesList.length > 0 ? '<div style="margin-top:0.3rem;font-size:0.75rem;color:var(--text-secondary);">' + resourcesList.join('<br>') + '</div>' : ''}
        `;
    }

    div.innerHTML = `
        <div class="feed-item-header">
            <span>${data.type || (isDispatch ? (data.priority_code || 'Dispatch') : 'Agent')}</span>
            <span>${timeAgo(timestamp)}</span>
        </div>
        <div class="feed-item-body">${message}</div>
        ${extraInfo}
    `;

    container.prepend(div);
    // Cap at 50 entries
    while (container.children.length > 50) {
        container.removeChild(container.lastChild);
    }
};

// ─── Predictions Panel ──────────────────────────────────────────────────────
const updatePredictions = (data) => {
    if (!data) return;

    const assessment = (typeof data.analysis === 'string' ? data.analysis : null) || data.risk_assessment || data.overall_assessment || data.summary || data.assessment || 'Analysis in progress...';
    let urgency = data.urgency_score;
    if (urgency === undefined || urgency === null) {
        const lvl = String(data.status || data.risk_level || '').toUpperCase();
        if (lvl.includes('CRITICAL')) urgency = 0.95;
        else if (lvl.includes('HIGH')) urgency = 0.75;
        else if (lvl.includes('MOD') || lvl.includes('MED')) urgency = 0.50;
        else urgency = 0.30;
    }
    const urgencyColor = urgency > 0.7 ? 'var(--danger)' : urgency > 0.4 ? 'var(--warning)' : 'var(--success)';

    let metricsHtml = '';
    if (data.key_metrics) {
        const km = data.key_metrics;
        metricsHtml = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin:0.6rem 0;padding:0.5rem;background:rgba(255,255,255,0.03);border-radius:6px;font-size:0.78rem;">
                <div><span style="color:var(--text-secondary)">Viability Index:</span> <strong style="color:${(km.viability_index || 0) < 0 ? 'var(--danger)' : 'var(--success)'}">${km.viability_index !== undefined ? km.viability_index : '--'}</strong></div>
                <div><span style="color:var(--text-secondary)">Total Acres:</span> <strong>${km.total_acres ? Number(km.total_acres).toLocaleString() : '--'} ac</strong></div>
                <div><span style="color:var(--text-secondary)">Active Fires:</span> <strong>${km.active_fires || km.new_fires || '--'}</strong></div>
                <div><span style="color:var(--text-secondary)">Containment:</span> <strong style="color:var(--danger)">${km.containment || '5%'}</strong></div>
            </div>
        `;
    }

    let fireDetails = '';
    const topList = (Array.isArray(data.fire_analyses) && data.fire_analyses.length > 0) ? data.fire_analyses :
                    (Array.isArray(data.top_priority_fires) && data.top_priority_fires.length > 0) ? data.top_priority_fires :
                    (Array.isArray(data.top_fires) && data.top_fires.length > 0) ? data.top_fires : [];

    if (topList.length > 0 && typeof topList[0] === 'object' && topList[0].fire_id) {
        fireDetails = '<div style="margin-top:0.8rem;">' + topList.slice(0, 5).map(f => `
            <div style="margin-bottom:0.5rem;padding:0.5rem;background:rgba(0,0,0,0.25);border-radius:6px;border-left:3px solid var(--danger);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <strong>${f.fire_name || f.fire_id}</strong>
                    <span class="badge badge-${(f.risk_level || 'critical').toLowerCase()}">${f.risk_level || 'CRITICAL'}</span>
                </div>
                ${f.predicted_spread ? `<div style="font-size:0.8rem;color:var(--text-secondary);margin-top:0.25rem;">${f.predicted_spread}</div>` : ''}
                ${f.key_concerns ? `<div style="font-size:0.75rem;color:var(--text-secondary);margin-top:0.2rem;">⚠️ ${Array.isArray(f.key_concerns) ? f.key_concerns.join(' · ') : f.key_concerns}</div>` : ''}
                ${f.recommended_action ? `<div style="font-size:0.75rem;color:var(--accent);margin-top:0.2rem;">🛡️ ${f.recommended_action}</div>` : ''}
            </div>
        `).join('') + '</div>';
    } else if (topList.length > 0) {
        fireDetails = '<div style="margin-top:0.8rem;"><div style="font-size:0.78rem;font-weight:600;color:var(--text-secondary);margin-bottom:0.4rem;">🔥 Top Priority Incidents:</div>' +
            topList.slice(0, 5).map(f => {
                const str = typeof f === 'string' ? f : (f.fire_name || f.name || JSON.stringify(f));
                return `
                <div style="margin-bottom:0.4rem;padding:0.45rem 0.6rem;background:rgba(255,255,255,0.03);border-left:3px solid var(--danger);border-radius:4px;font-size:0.8rem;color:var(--text-primary);">
                    ${str}
                </div>`;
            }).join('') + '</div>';
    }

    let hotspotsHtml = '';
    if (Array.isArray(data.ignition_hotspots) && data.ignition_hotspots.length > 0) {
        hotspotsHtml = `
            <div style="margin-top:0.6rem;">
                <div style="font-size:0.78rem;font-weight:600;color:var(--accent);margin-bottom:0.3rem;">🔮 24-Hour ML Predictive Hotspots:</div>
                ${data.ignition_hotspots.slice(0, 3).map(h => `
                    <div style="font-size:0.78rem;color:var(--text-secondary);margin-bottom:0.25rem;padding:0.25rem 0.4rem;background:rgba(255,255,255,0.02);border-radius:4px;">
                        📍 ${typeof h === 'string' ? h : `${h.grid_id || ''} (${h.province || ''}): ${h.risk || ''}`}
                    </div>
                `).join('')}
            </div>
        `;
    }

    const recommendation = data.system_recommendation || data.recommendation || '';

    els.predictions.innerHTML = `
        <div style="margin-bottom:0.6rem;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:600;font-size:0.92rem;">🤖 Executive Risk Assessment</span>
            <span style="color:${urgencyColor};font-weight:700;font-size:0.82rem;padding:0.15rem 0.5rem;background:rgba(255,255,255,0.05);border-radius:4px;">
                Urgency: ${(urgency * 100).toFixed(0)}%
            </span>
        </div>
        <p style="color:var(--text-primary);font-size:0.88rem;line-height:1.45;margin-bottom:0.5rem;">${assessment}</p>
        ${metricsHtml}
        ${recommendation ? `<p style="margin-top:0.5rem;font-size:0.85rem;color:var(--secondary);padding:0.4rem 0.6rem;background:rgba(14,165,233,0.08);border-left:3px solid var(--secondary);border-radius:4px;">📋 <strong>Recommendation:</strong> ${recommendation}</p>` : ''}
        ${hotspotsHtml}
        ${fireDetails}
    `;
};

// ─── Jev AI Supervisor Panel ────────────────────────────────────────────────
const updateJevPanel = (data) => {
    if (!data) return;
    const d = data.last_decision || data;
    if (!d || d.timestamp === undefined) return;

    if (els.jevStatusBadge) {
        if (d.error) {
            els.jevStatusBadge.textContent = 'Degraded';
            els.jevStatusBadge.className = 'badge badge-critical';
        } else {
            els.jevStatusBadge.textContent = 'Active';
            els.jevStatusBadge.className = 'badge badge-safe';
        }
    }

    const threatPct = Math.round((d.is_immediate_threat || 0) * 100);
    const dispatchPct = Math.round((d.requires_emergency_dispatch || 0) * 100);
    const overridePct = Math.round((d.avf_override_recommended || 0) * 100);

    if (els.jevThreatVal) els.jevThreatVal.textContent = `${threatPct}%`;
    if (els.jevThreatBar) els.jevThreatBar.style.width = `${threatPct}%`;

    if (els.jevDispatchVal) els.jevDispatchVal.textContent = `${dispatchPct}%`;
    if (els.jevDispatchBar) els.jevDispatchBar.style.width = `${dispatchPct}%`;

    if (els.jevOverrideVal) els.jevOverrideVal.textContent = `${overridePct}%`;
    if (els.jevOverrideBar) els.jevOverrideBar.style.width = `${overridePct}%`;

    const level = (d.recommended_response_level || 'MONITOR').toUpperCase();
    if (els.jevResponseLevel) {
        els.jevResponseLevel.textContent = level;
        els.jevResponseLevel.className = `jev-response-level jev-level-${level.toLowerCase()}`;
    }
    if (els.jevResponseConf) {
        const conf = Math.round((d.response_level_confidence || 0) * 100);
        els.jevResponseConf.textContent = `conf: ${conf}%`;
    }

    if (els.jevSeverityScore) {
        const score = typeof d.overall_severity_score === 'number' ? d.overall_severity_score.toFixed(1) : '--';
        els.jevSeverityScore.textContent = `${score} / 3.0`;
    }
    if (els.jevSeverityConf) {
        const sConf = Math.round((d.severity_confidence || 0) * 100);
        els.jevSeverityConf.textContent = `conf: ${sConf}%`;
    }

    if (els.jevLatency) {
        els.jevLatency.textContent = `⏱ ${Math.round(d.latency_ms || 0)}ms`;
    }

    if (els.jevOverrideStatus) {
        if (overridePct >= 85) {
            els.jevOverrideStatus.textContent = '⚡ Override Active';
            els.jevOverrideStatus.className = 'jev-override-status active';
        } else {
            els.jevOverrideStatus.textContent = 'AVF Synchronized';
            els.jevOverrideStatus.className = 'jev-override-status';
        }
    }
};

// ─── SSE Connection ─────────────────────────────────────────────────────────
const connectSSE = () => {
    if (eventSource) eventSource.close();

    els.connDot.className = 'pulse-dot';
    els.connStatus.textContent = 'Connecting...';

    try {
        eventSource = new EventSource('/stream');

        eventSource.addEventListener('connected', () => {
            els.connDot.className = 'pulse-dot';
            els.connDot.classList.remove('disconnected');
            els.connStatus.textContent = 'Live Monitoring';
            reconnectDelay = 1000;
        });

        eventSource.addEventListener('fire_update', (e) => {
            const data = JSON.parse(e.data);
            const fires = data.fires || [];
            updateFireMarkers(fires);
            renderFiresTable(fires);

            const totalAcres = fires.reduce((sum, f) => sum + (f.daily_acres || 0), 0);
            const totalHa = fires.reduce((sum, f) => sum + (f.hectares || Math.round((f.daily_acres || 0) / 2.47105)), 0);
            animateValue(els.statFires, currentStats.activeFires, fires.length, 500);
            els.statAcres.textContent = `${formatNumber(totalHa)} ha (${formatNumber(totalAcres)} ac)`;
            currentStats.activeFires = fires.length;
            currentStats.totalAcres = totalAcres;
        });

        eventSource.addEventListener('governance_update', (e) => {
            const data = JSON.parse(e.data);
            updateVIGauge(data.viability_index);
            updateVIComponents(data.c1_safety, data.c2_fairness, data.c3_stability);

            // Update t* stat
            if (data.t_star !== null && data.t_star !== undefined) {
                const tMin = (data.t_star / 60).toFixed(1);
                els.statTTV.textContent = `${tMin} min`;
                els.statTTV.style.color = data.t_star < 300 ? 'var(--danger)' : 'var(--warning)';
            } else {
                els.statTTV.textContent = 'Safe ✓';
                els.statTTV.style.color = 'var(--success)';
            }
        });

        eventSource.addEventListener('prediction', (e) => {
            const data = JSON.parse(e.data);
            updatePredictions(data);
        });

        eventSource.addEventListener('action', (e) => {
            const data = JSON.parse(e.data);
            addFeedItem(els.feed, data, false);
        });

        eventSource.addEventListener('dispatch', (e) => {
            const data = JSON.parse(e.data);
            addFeedItem(els.dispatch, data, true);
        });

        eventSource.addEventListener('jev_decision', (e) => {
            const data = JSON.parse(e.data);
            updateJevPanel(data);
        });

        eventSource.addEventListener('heartbeat', (e) => {
            const data = JSON.parse(e.data);
            if (data.status === 'online' || data.status === 'keepalive') {
                els.connDot.className = 'pulse-dot';
                els.connDot.classList.remove('disconnected');
                els.connStatus.textContent = `Live · Cycle #${data.cycle || '—'}`;
            }
        });

        eventSource.onerror = () => {
            els.connDot.classList.add('disconnected');
            els.connStatus.textContent = 'Reconnecting...';
            eventSource.close();
            // Exponential backoff
            setTimeout(connectSSE, reconnectDelay);
            reconnectDelay = Math.min(reconnectDelay * 2, 30000);
        };

    } catch (err) {
        console.error('SSE setup failed:', err);
        setTimeout(connectSSE, 5000);
    }
};

// ─── Initial Data Load ──────────────────────────────────────────────────────
const loadInitialData = async () => {
    try {
        const [fireRes, viRes, predRes, dispRes] = await Promise.all([
            fetch('/api/fires').catch(() => null),
            fetch('/api/viability').catch(() => null),
            fetch('/api/predictions').catch(() => null),
            fetch('/api/dispatches').catch(() => null),
        ]);

        if (fireRes && fireRes.ok) {
            const data = await fireRes.json();
            const fires = data.fires || [];
            updateFireMarkers(fires);
            renderFiresTable(fires);
            currentStats.activeFires = fires.length;
            currentStats.totalAcres = fires.reduce((sum, f) => sum + (f.daily_acres || 0), 0);
            els.statFires.textContent = formatNumber(currentStats.activeFires);
            els.statAcres.textContent = formatNumber(currentStats.totalAcres);
        }

        if (viRes && viRes.ok) {
            const data = await viRes.json();
            updateVIGauge(data.viability_index || 0);
            updateVIComponents(data.c1_safety || 0, data.c2_fairness || 0, data.c3_stability || 0);
        }

        if (predRes && predRes.ok) {
            const data = await predRes.json();
            if (data.analysis) updatePredictions(data.analysis);
        }

        if (dispRes && dispRes.ok) {
            const data = await dispRes.json();
            const dispatches = data.dispatches || [];
            if (els.dispatch && dispatches.length > 0) {
                els.dispatch.innerHTML = '';
                for (const d of [...dispatches].reverse()) {
                    addFeedItem(els.dispatch, d, true, true);
                }
            }
        }

        fetch('/api/jev')
            .then(r => r.json())
            .then(data => {
                if (data) updateJevPanel(data);
            })
            .catch(() => null);

        loadTopPredictionsTable();
    } catch (e) {
        console.log('Initial data load failed (will populate via SSE):', e);
    }
};

// ─── Initialize ─────────────────────────────────────────────────────────────
const init = () => {
    initMap();
    loadInitialData();
    connectSSE();
};

document.addEventListener('DOMContentLoaded', init);
