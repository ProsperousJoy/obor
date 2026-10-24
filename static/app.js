/**
 * app.js — Frontend Logic for OBOR
 * Borneo Field Operations Instrument
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

// ─── Live Clock (WITA / UTC+8) ──────────────────────────────────────────────
const updateWitaClock = () => {
    const el = document.getElementById('clock-wita');
    if (!el) return;
    const now = new Date();
    const utcMs = now.getTime() + now.getTimezoneOffset() * 60000;
    const wita = new Date(utcMs + 8 * 3600000);
    const pad = (n) => String(n).padStart(2, '0');
    el.textContent = `${pad(wita.getHours())}:${pad(wita.getMinutes())}:${pad(wita.getSeconds())} WITA`;
};
setInterval(updateWitaClock, 1000);
updateWitaClock();

// ─── Utilities ──────────────────────────────────────────────────────────────
const formatNumber = (num) => new Intl.NumberFormat().format(Math.round(num));

const stripEmoji = (str) => {
    if (!str || typeof str !== 'string') return '';
    return str.replace(/[\u{1F300}-\u{1F9FF}\u{2600}-\u{27BF}\u{1F100}-\u{1F1FF}\u{1F200}-\u{1F2FF}\u{1F680}-\u{1F6FF}\u{1F004}\u{1F0CF}\u{1F900}-\u{1F9FF}\u{FE00}-\u{FE0F}]/gu, '')
              .replace(/\s{2,}/g, ' ')
              .trim();
};

const timeAgo = (ts) => {
    const now = Date.now();
    const then = typeof ts === 'number'
        ? (ts > 1e12 ? ts : ts * 1000)
        : new Date(ts).getTime();
    const diffSec = (now - then) / 1000;
    if (diffSec < 60) return 'Just now';
    if (diffSec < 3600) return `${Math.floor(diffSec / 60)}m ago`;
    if (diffSec < 86400) return `${Math.floor(diffSec / 3600)}h ago`;
    return `${Math.floor(diffSec / 86400)}d ago`;
};

const interpolateColor = (val) => {
    // val in [-1, +1] -> Flame Red (-1: #C4452F) -> Gold (0: #C99A3E) -> Olive (+1: #8A9A72)
    const t = Math.max(0, Math.min(1, (val + 1) / 2));
    if (t < 0.5) {
        const p = t / 0.5;
        // From (196, 69, 47) to (201, 154, 62)
        const r = Math.round(196 + (201 - 196) * p);
        const g = Math.round(69 + (154 - 69) * p);
        const b = Math.round(47 + (62 - 47) * p);
        return `rgb(${r}, ${g}, ${b})`;
    } else {
        const p = (t - 0.5) / 0.5;
        // From (201, 154, 62) to (138, 154, 114)
        const r = Math.round(201 + (138 - 201) * p);
        const g = Math.round(154 + (154 - 154) * p);
        const b = Math.round(62 + (114 - 62) * p);
        return `rgb(${r}, ${g}, ${b})`;
    }
};

const animateValue = (el, start, end, duration) => {
    if (!el) return;
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
        gain.gain.setValueAtTime(0.06, audioCtx.currentTime);
        gain.gain.exponentialRampToValueAtTime(0.001, audioCtx.currentTime + 0.5);
        osc.connect(gain);
        gain.connect(audioCtx.destination);
        osc.start();
        osc.stop(audioCtx.currentTime + 0.5);
    } catch (e) {
        console.warn('Audio alert failed:', e);
    }
};

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

    map.createPane('labels');
    map.getPane('labels').style.zIndex = 450;
    map.getPane('labels').style.pointerEvents = 'none';

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
                html: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="3" y="4" width="18" height="16" rx="1"/><path d="M7 8h10M7 12h10M7 16h6"/></svg>',
                iconSize: [22, 22],
                iconAnchor: [11, 11]
            });
            const marker = L.marker([hq.lat, hq.lon], { icon });
            marker.bindPopup(`
                <div style="font-family:'IBM Plex Mono', 'Archivo', monospace;min-width:210px;font-size:11px;color:#E9E2D4;">
                    <strong style="color:#D95F2B;font-size:12px;letter-spacing:0.04em;">${hq.name}</strong><br>
                    <span style="color:#948B7E;">${hq.province || ''} &bull; ${hq.regency || ''}</span><br><br>
                    CREW ON DUTY: <strong>${hq.crew || 10} FIREFIGHTERS</strong><br>
                    RADIO FREQ: <strong>${hq.radio || 'VHF 142.5 MHz'}</strong><br>
                    AGENCY: <strong>${hq.agency || 'MANGGALA AGNI'}</strong>
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
                html: '<svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><path d="M12 2.7l5.7 5.7a8 8 0 1 1-11.4 0z"/></svg>',
                iconSize: [20, 20],
                iconAnchor: [10, 10]
            });
            const marker = L.marker([w.lat, w.lon], { icon });
            marker.bindPopup(`
                <div style="font-family:'IBM Plex Mono', 'Archivo', monospace;min-width:200px;font-size:11px;color:#E9E2D4;">
                    <strong style="color:#8A9A72;font-size:12px;letter-spacing:0.04em;">${w.name}</strong><br>
                    <span style="color:#948B7E;">${w.province || ''}</span><br><br>
                    TYPE: <strong>${w.type}</strong><br>
                    CAPACITY: <strong>${formatNumber(w.capacity_m3 || 0)} m³</strong><br>
                    PUMP ACCESS: <strong>OPERATIONAL</strong>
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
            const coords = feat.geometry.coordinates;
            const p = feat.properties;
            const riskPct = (p.calibrated_risk * 100).toFixed(1);
            
            let color = '#C99A3E'; // WASPADA
            let radius = 6;
            if (p.risk_tier.includes('AWAS')) {
                color = '#C4452F';
                radius = 10;
            } else if (p.risk_tier.includes('SIAGA')) {
                color = '#D9762B';
                radius = 8;
            }

            const marker = L.circleMarker([coords[1], coords[0]], {
                radius: radius,
                fillColor: color,
                color: '#100F0D',
                weight: 1,
                opacity: 0.9,
                fillOpacity: 0.8
            });

            const cleanEta = p.estimated_eta ? p.estimated_eta.replace(/⚡/g, '').trim() : '3-6 jam (Siang Ini)';

            marker.bindPopup(`
                <div style="font-family:'IBM Plex Mono', 'Archivo', monospace;min-width:220px;font-size:11px;color:#E9E2D4;">
                    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px;border-bottom:1px solid #2B2721;padding-bottom:4px;">
                        <strong style="color:${color};font-size:11px;letter-spacing:0.04em;">24H ML RISK ESTIMATE</strong>
                        <span style="font-size:10px;background:#100F0D;border:1px solid #2B2721;padding:1px 5px;">${p.grid_id}</span>
                    </div>
                    <span style="color:#948B7E;">REGION: ${p.province || 'Kalimantan'}</span><br><br>
                    ALERT TIER: <strong style="color:${color}">${p.risk_tier}</strong><br>
                    PROBABILITY: <strong>${riskPct}%</strong><br>
                    ETA WINDOW: <strong style="color:#E9E2D4;">${cleanEta}</strong><br>
                    PREDICTED FRP: <strong>${p.predicted_frp_mw} MW</strong><br>
                    CONSECUTIVE DRY DAYS: <strong>${p.dry_days} hari</strong><br>
                    <hr style="border:none;border-top:1px solid #2B2721;margin:6px 0;">
                    <span style="font-size:9.5px;color:#948B7E;">MODEL: XGBoost + LightGBM Regressor</span>
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
            els.predictionTable.innerHTML = '<tr><td colspan="8" class="table-empty">Tidak ada sel risiko tinggi yang terdeteksi saat ini.</td></tr>';
            return;
        }

        els.predictionTable.innerHTML = cells.map(c => {
            const riskPct = (c.calibrated_risk * 100).toFixed(1);
            let badgeClass = 'badge-waspada';
            if (c.risk_tier.includes('AWAS')) badgeClass = 'badge-awas';
            else if (c.risk_tier.includes('SIAGA')) badgeClass = 'badge-siaga';
            else if (c.risk_tier.includes('NORMAL')) badgeClass = 'badge-normal';

            const cleanEta = c.estimated_eta ? c.estimated_eta.replace(/⚡/g, '').trim() : '2-5 jam (13:00-16:30)';

            return `
                <tr>
                    <td><strong>${c.grid_id}</strong></td>
                    <td>${c.province || 'Kalimantan'}</td>
                    <td><strong>${riskPct}%</strong> <span style="font-size:10px;color:var(--muted);">(raw ${(c.raw_risk * 100).toFixed(0)}%)</span></td>
                    <td><span class="badge ${badgeClass}">${c.risk_tier}</span></td>
                    <td><span style="color:var(--bone);font-weight:600;font-size:11px;">${cleanEta}</span></td>
                    <td><span style="color:var(--sev-siaga);font-weight:600;">${c.predicted_frp_mw} MW</span></td>
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
    'MONITOR': '#8A9A72',
    'WATCH': '#C99A3E',
    'WARNING': '#D9762B',
    'EMERGENCY': '#C4452F',
}[level] || '#948B7E');

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
        const radius = Math.max(5, Math.min(Math.sqrt(ha) * 1.4, 30));
        const color = isPeat ? '#C4452F' : getAlertColor(alert);
        const textColor = (isPeat || alert === 'EMERGENCY') ? '#E07A60' : color;

        let weatherInfo = '';
        if (fire.weather) {
            weatherInfo = `TEMP: ${fire.weather.temperature_c}°C &bull; HUM: ${fire.weather.humidity_pct}% &bull; WIND: ${fire.weather.wind_speed_kph} km/h`;
        }

        const popupContent = `
            <div style="font-family:'IBM Plex Mono', 'Archivo', monospace;min-width:210px;font-size:11px;color:#E9E2D4;">
                <strong style="font-size:13px;color:#E9E2D4;">${name}</strong><br>
                <span style="color:#948B7E;">${fire.province || fire.state || ''} &bull; ${fire.county || ''}</span><br>
                ${isPeat ? '<span class="peat-tag">GAMBUT // PEATLAND</span>' : '<span class="mineral-tag">MINERAL FOREST</span>'}<br><br>
                AREA: <strong>${formatNumber(ha)} ha</strong> (${formatNumber(acres)} ac)<br>
                CONTAINED: <strong>${contained.toFixed(0)}%</strong><br>
                ALERT TIER: <strong style="color:${textColor}">${alert}</strong>
                ${weatherInfo ? '<br><span style="color:#948B7E;">' + weatherInfo + '</span>' : ''}
            </div>
        `;

        if (fireMarkers.has(id)) {
            const marker = fireMarkers.get(id);
            marker.setLatLng([lat, lon]);
            marker.setRadius(radius);
            marker.setStyle({ color: '#100F0D', fillColor: color, fillOpacity: isPeat ? 0.8 : 0.65, weight: 1 });
            marker.setPopupContent(popupContent);
        } else {
            const marker = L.circleMarker([lat, lon], {
                radius, color: '#100F0D', fillColor: color, fillOpacity: isPeat ? 0.8 : 0.65, weight: 1
            }).addTo(fireLayerGroup);
            marker.bindPopup(popupContent);
            marker.on('click', () => map.flyTo([lat, lon], 8, { duration: 1.2 }));
            fireMarkers.set(id, marker);
        }
    });

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

        let trendHtml = '<span style="color:var(--muted)">=</span>';
        if (fire.acre_change > 50) {
            trendHtml = '<span style="color:var(--sev-awas);font-weight:700;">+</span>';
        } else if (fire.acre_change < -20) {
            trendHtml = '<span style="color:var(--olive);font-weight:700;">-</span>';
        }

        tr.innerHTML = `
            <td><strong>${fire.name || 'Unknown'}</strong></td>
            <td>${fire.province || fire.state || '—'} / ${fire.county || '—'}</td>
            <td><strong>${formatNumber(ha)} ha</strong> <span style="color:var(--muted);font-size:0.75rem;">(${formatNumber(acres)} ac)</span></td>
            <td>${contained}%</td>
            <td>${isPeat ? '<span class="peat-tag">GAMBUT</span>' : '<span class="mineral-tag">MINERAL</span>'}</td>
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
    if (els.viGaugePath) {
        els.viGaugePath.style.strokeDasharray = `${dashLength} ${maxDash}`;
    }

    animateValue(els.viGaugeText, currentStats.vi, vi, 500);
    animateValue(els.statVI, currentStats.vi, vi, 500);
    currentStats.vi = vi;
};

const updateVIComponents = (c1, c2, c3) => {
    if (els.valC1) els.valC1.textContent = c1.toFixed(2);
    if (els.valC2) els.valC2.textContent = c2.toFixed(2);
    if (els.valC3) els.valC3.textContent = c3.toFixed(2);

    if (els.barC1) {
        els.barC1.style.width = `${((c1 + 1) / 2) * 100}%`;
        els.barC1.style.backgroundColor = interpolateColor(c1);
    }
    if (els.barC2) {
        els.barC2.style.width = `${((c2 + 1) / 2) * 100}%`;
        els.barC2.style.backgroundColor = interpolateColor(c2);
    }
    if (els.barC3) {
        els.barC3.style.width = `${((c3 + 1) / 2) * 100}%`;
        els.barC3.style.backgroundColor = interpolateColor(c3);
    }
};

// ─── Feed Items ─────────────────────────────────────────────────────────────
const addFeedItem = (container, data, isDispatch = false, isInitial = false) => {
    if (!container) return;
    const div = document.createElement('div');
    div.className = `feed-item ${isDispatch ? 'dispatch-item' : ''}`;

    if (isDispatch && !isInitial) {
        div.classList.add('shake-anim');
        playEmergencyAlert();
    }

    const rawMessage = data.message || data.fire_name || JSON.stringify(data);
    const message = stripEmoji(rawMessage);
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
            resourcesList = data.resources_deployed.map(r => r.display || r.name || 'Resource');
        }
        resourcesList = resourcesList.map(r => stripEmoji(typeof r === 'string' ? r : (r.display || r.name || 'Resource')));

        extraInfo = `
            <div style="margin-top:0.35rem;font-size:0.75rem;color:var(--muted);font-family:var(--font-mono);">
                ${severity ? '[' + severity + ']' : ''}
                ${personnel ? ' &bull; PERS: ' + personnel : ''}
                ${eta ? ' &bull; ETA: ' + eta + 'm' : ''}
                ${evac ? ' &bull; [EVACUATION MANDATE]' : ''}
                ${station ? '<br>BASE: ' + station : ''}
            </div>
            ${resourcesList.length > 0 ? '<div style="margin-top:0.25rem;font-size:0.72rem;color:var(--faint);font-family:var(--font-mono);">' + resourcesList.join('<br>') + '</div>' : ''}
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
    while (container.children.length > 50) {
        container.removeChild(container.lastChild);
    }
};

// ─── Predictions Panel ──────────────────────────────────────────────────────
const updatePredictions = (data) => {
    if (!data || !els.predictions) return;

    const rawAssessment = (typeof data.analysis === 'string' ? data.analysis : null) || data.risk_assessment || data.overall_assessment || data.summary || data.assessment || 'Analisis risiko operasional sedang berjalan...';
    const assessment = stripEmoji(rawAssessment);
    let urgency = data.urgency_score;
    if (urgency === undefined || urgency === null) {
        const lvl = String(data.status || data.risk_level || '').toUpperCase();
        if (lvl.includes('CRITICAL')) urgency = 0.95;
        else if (lvl.includes('HIGH')) urgency = 0.75;
        else if (lvl.includes('MOD') || lvl.includes('MED')) urgency = 0.50;
        else urgency = 0.30;
    }
    const urgencyColor = urgency > 0.7 ? 'var(--sev-awas)' : urgency > 0.4 ? 'var(--sev-siaga)' : 'var(--olive)';

    let metricsHtml = '';
    if (data.key_metrics) {
        const km = data.key_metrics;
        metricsHtml = `
            <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.4rem;margin:0.6rem 0;padding:0.6rem;background:var(--ground);border:1px solid var(--hairline);font-size:0.75rem;">
                <div><span style="color:var(--muted)">Viability Index:</span> <strong style="color:${(km.viability_index || 0) < 0 ? 'var(--sev-awas)' : 'var(--olive)'}">${km.viability_index !== undefined ? km.viability_index : '--'}</strong></div>
                <div><span style="color:var(--muted)">Total Area:</span> <strong>${km.total_acres ? Number(km.total_acres).toLocaleString() : '--'} ac</strong></div>
                <div><span style="color:var(--muted)">Active Fires:</span> <strong>${km.active_fires || km.new_fires || '--'}</strong></div>
                <div><span style="color:var(--muted)">Containment:</span> <strong style="color:var(--sev-awas)">${km.containment || '5%'}</strong></div>
            </div>
        `;
    }

    let fireDetails = '';
    const topList = (Array.isArray(data.fire_analyses) && data.fire_analyses.length > 0) ? data.fire_analyses :
                    (Array.isArray(data.top_priority_fires) && data.top_priority_fires.length > 0) ? data.top_priority_fires :
                    (Array.isArray(data.top_fires) && data.top_fires.length > 0) ? data.top_fires : [];

    if (topList.length > 0 && typeof topList[0] === 'object' && topList[0].fire_id) {
        fireDetails = '<div style="margin-top:0.75rem;">' + topList.slice(0, 5).map(f => `
            <div style="margin-bottom:0.45rem;padding:0.5rem 0.65rem;background:var(--ground);border:1px solid var(--hairline);">
                <div style="display:flex;justify-content:space-between;align-items:center;">
                    <strong>${f.fire_name || f.fire_id}</strong>
                    <span class="badge badge-${(f.risk_level || 'critical').toLowerCase()}">${f.risk_level || 'CRITICAL'}</span>
                </div>
                ${f.predicted_spread ? `<div style="font-size:0.75rem;color:var(--muted);margin-top:0.25rem;">${f.predicted_spread}</div>` : ''}
                ${f.key_concerns ? `<div style="font-size:0.72rem;color:var(--muted);margin-top:0.2rem;">CONCERN: ${Array.isArray(f.key_concerns) ? f.key_concerns.join(' &bull; ') : f.key_concerns}</div>` : ''}
                ${f.recommended_action ? `<div style="font-size:0.72rem;color:var(--bone);margin-top:0.2rem;">ACTION: ${f.recommended_action}</div>` : ''}
            </div>
        `).join('') + '</div>';
    } else if (topList.length > 0) {
        fireDetails = '<div style="margin-top:0.75rem;"><div style="font-size:0.72rem;font-weight:600;color:var(--muted);margin-bottom:0.35rem;text-transform:uppercase;">PRIORITY INCIDENTS:</div>' +
            topList.slice(0, 5).map(f => {
                const str = typeof f === 'string' ? f : (f.fire_name || f.name || JSON.stringify(f));
                return `
                <div style="margin-bottom:0.35rem;padding:0.4rem 0.55rem;background:var(--ground);border:1px solid var(--hairline);font-size:0.75rem;color:var(--bone);">
                    ${str}
                </div>`;
            }).join('') + '</div>';
    }

    let hotspotsHtml = '';
    if (Array.isArray(data.ignition_hotspots) && data.ignition_hotspots.length > 0) {
        hotspotsHtml = `
            <div style="margin-top:0.6rem;">
                <div style="font-size:0.72rem;font-weight:600;color:var(--ember);margin-bottom:0.3rem;text-transform:uppercase;">24H ML PREDICTIVE HOTSPOTS:</div>
                ${data.ignition_hotspots.slice(0, 3).map(h => `
                    <div style="font-size:0.72rem;color:var(--muted);margin-bottom:0.2rem;padding:0.25rem 0.45rem;background:var(--ground);border:1px solid var(--hairline-subtle);">
                        CELL: ${typeof h === 'string' ? h : `${h.grid_id || ''} (${h.province || ''}): ${h.risk || ''}`}
                    </div>
                `).join('')}
            </div>
        `;
    }

    const rawRec = data.system_recommendation || data.recommendation || '';
    const recommendation = stripEmoji(rawRec);

    els.predictions.innerHTML = `
        <div style="margin-bottom:0.6rem;display:flex;justify-content:space-between;align-items:center;">
            <span style="font-weight:600;font-size:0.85rem;letter-spacing:0.06em;text-transform:uppercase;">EXECUTIVE RISK DIRECTIVE</span>
            <span style="color:var(--bone);font-weight:700;font-size:0.75rem;padding:0.15rem 0.45rem;background:var(--ground);border:1px solid var(--hairline);border-left:2px solid ${urgencyColor};">
                URGENCY: ${(urgency * 100).toFixed(0)}%
            </span>
        </div>
        <p style="color:var(--bone);font-size:0.8rem;line-height:1.45;margin-bottom:0.5rem;">${assessment}</p>
        ${metricsHtml}
        ${recommendation ? `<div style="margin-top:0.5rem;font-size:0.78rem;color:var(--bone);padding:0.45rem 0.6rem;background:var(--ground);border:1px solid var(--hairline);"><strong>DIRECTIVE:</strong> ${recommendation}</div>` : ''}
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
            els.jevStatusBadge.textContent = 'DEGRADED';
            els.jevStatusBadge.className = 'badge badge-critical';
        } else {
            els.jevStatusBadge.textContent = 'ACTIVE';
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
        els.jevResponseLevel.className = `jev-response-level font-mono jev-level-${level.toLowerCase()}`;
    }
    if (els.jevResponseConf) {
        const conf = Math.round((d.response_level_confidence || 0) * 100);
        els.jevResponseConf.textContent = `CONF: ${conf}%`;
    }

    if (els.jevSeverityScore) {
        const score = typeof d.overall_severity_score === 'number' ? d.overall_severity_score.toFixed(1) : '--';
        els.jevSeverityScore.textContent = `${score} / 3.0`;
    }
    if (els.jevSeverityConf) {
        const sConf = Math.round((d.severity_confidence || 0) * 100);
        els.jevSeverityConf.textContent = `CONF: ${sConf}%`;
    }

    if (els.jevLatency) {
        els.jevLatency.textContent = `LATENCY: ${Math.round(d.latency_ms || 0)}ms`;
    }

    if (els.jevOverrideStatus) {
        if (overridePct >= 85) {
            els.jevOverrideStatus.textContent = 'OVERRIDE ACTIVE';
            els.jevOverrideStatus.className = 'jev-override-status font-mono active';
        } else {
            els.jevOverrideStatus.textContent = 'SYNCHRONIZED';
            els.jevOverrideStatus.className = 'jev-override-status font-mono';
        }
    }
};

// ─── SSE Connection ─────────────────────────────────────────────────────────
const connectSSE = () => {
    if (eventSource) eventSource.close();

    els.connDot.className = 'pulse-dot';
    els.connStatus.textContent = 'CONNECTING...';

    try {
        eventSource = new EventSource('/stream');

        eventSource.addEventListener('connected', () => {
            els.connDot.className = 'pulse-dot';
            els.connDot.classList.remove('disconnected');
            els.connStatus.textContent = 'ONLINE // STREAMING';
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

            if (data.t_star !== null && data.t_star !== undefined) {
                const tMin = (data.t_star / 60).toFixed(1);
                els.statTTV.textContent = `${tMin} min`;
                els.statTTV.style.color = data.t_star < 300 ? 'var(--sev-awas)' : 'var(--sev-waspada)';
            } else {
                els.statTTV.textContent = 'NOMINAL';
                els.statTTV.style.color = 'var(--olive)';
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
                els.connStatus.textContent = `CYCLE #${data.cycle || '—'}`;
            }
        });

        eventSource.onerror = () => {
            els.connDot.classList.add('disconnected');
            els.connStatus.textContent = 'RECONNECTING...';
            eventSource.close();
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
