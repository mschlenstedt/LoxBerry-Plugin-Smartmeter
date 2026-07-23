(function (root, factory) {
	const api = factory();
	if (typeof module === "object" && module.exports) module.exports = api;
	else root.SmartMeterLive = api;
}(typeof globalThis !== "undefined" ? globalThis : this, function () {
	"use strict";

	const STORAGE_KEY = "smartmeter-v2.vzloggerLiveCharts.v1";
	const POLL_INTERVAL = 2000;
	const GAP_INTERVAL = POLL_INTERVAL * 3;
	const POWER_CATEGORIES = new Set(["active_power_total", "active_power_import", "active_power_export"]);
	const ENERGY_CATEGORIES = new Set(["active_energy_import", "active_energy_export"]);
	const PALETTE = ["#0072b2", "#d55e00", "#009e73", "#cc79a7", "#e69f00", "#56b4e9", "#6f4e7c", "#555555"];
	const DASHES = [[], [8, 4], [2, 3], [10, 3, 2, 3]];

	function numericTimestamp(value) {
		const number = Number(value);
		if (!Number.isFinite(number)) return null;
		return Math.abs(number) < 100000000000 ? number * 1000 : number;
	}

	function scaledValue(value, meta) {
		const number = Number(value);
		const factor = Number(meta && meta.display_factor !== undefined ? meta.display_factor : 1);
		return Number.isFinite(number) && Number.isFinite(factor) ? number * factor : null;
	}

	function category(meta) {
		return String(meta && meta.category || "unknown");
	}

	function isPower(meta) { return POWER_CATEGORIES.has(category(meta)); }
	function isEnergy(meta) { return ENERGY_CATEGORIES.has(category(meta)); }

	function chartValue(value, meta) {
		if (!Number.isFinite(value)) return null;
		if (category(meta) === "active_power_export") return -Math.abs(value);
		if (category(meta) === "active_power_import") return Math.abs(value);
		return value;
	}

	function isTotalEnergyIdentifier(identifier, direction) {
		const wanted = direction === "export" ? "2" : "1";
		return new RegExp("(?:^|:)" + wanted + "\\.8\\.0(?:\\*\\d+)?$").test(String(identifier || ""));
	}

	function chooseEnergyChannel(items, direction) {
		const wantedCategory = direction === "export" ? "active_energy_export" : "active_energy_import";
		const matches = items.filter(item => category(item.meta) === wantedCategory && isTotalEnergyIdentifier(item.meta.identifier, direction));
		const canonical = matches.filter(item => !/\*/.test(String(item.meta.identifier || "")));
		if (canonical.length === 1) return canonical[0];
		return matches.length === 1 ? matches[0] : null;
	}

	function choosePowerChannels(items) {
		const totals = items.filter(item => category(item.meta) === "active_power_total");
		if (totals.length) return [totals.sort(channelOrder)[0]];
		return items.filter(item => category(item.meta) === "active_power_import" || category(item.meta) === "active_power_export").sort(channelOrder);
	}

	function channelOrder(a, b) {
		return Number(a.meta.channel_index || 0) - Number(b.meta.channel_index || 0);
	}

	function defaultSelection(channels) {
		const selected = new Set();
		const groups = new Map();
		channels.forEach(item => {
			const serial = String(item.meta.serial || "unknown");
			if (!groups.has(serial)) groups.set(serial, []);
			groups.get(serial).push(item);
		});
		groups.forEach(items => {
			choosePowerChannels(items).forEach(item => selected.add(item.uuid));
			const imported = chooseEnergyChannel(items, "import");
			const exported = chooseEnergyChannel(items, "export");
			if (imported) selected.add(imported.uuid);
			if (exported) selected.add(exported.uuid);
		});
		if (!selected.size) {
			const units = new Set();
			channels.slice().sort(channelOrder).forEach(item => {
				const unit = String(item.meta.unit || "");
				if (units.has(unit) || units.size < 2) {
					selected.add(item.uuid);
					units.add(unit);
				}
			});
		}
		return selected;
	}

	function cleanPreferences(input, availableUuids) {
		const valid = input && input.schema === 1 && Array.isArray(input.channels);
		if (!valid) return null;
		const available = new Set(availableUuids);
		return {
			schema: 1,
			channels: input.channels.filter(uuid => available.has(String(uuid).toLowerCase())).map(uuid => String(uuid).toLowerCase()),
			energyMode: input.energyMode === "absolute" ? "absolute" : "since-open",
			backgroundCollection: input.backgroundCollection === true
		};
	}

	function limitSelection(channels, wanted, maximumUnits) {
		const result = new Set(), units = new Set(), limit = maximumUnits || 2;
		channels.slice().sort(channelOrder).forEach(item => {
			if (!wanted.has(item.uuid)) return;
			const unit = String(item.meta.unit || "");
			if (units.has(unit) || units.size < limit) {
				units.add(unit);
				result.add(item.uuid);
			}
		});
		return result;
	}

	function hasReadingGap(previousTimestamp, timestamp) {
		return Number.isFinite(previousTimestamp) && Number.isFinite(timestamp) && timestamp - previousTimestamp > GAP_INTERVAL;
	}

	function isCounterReset(meta, previousValue, value) {
		return isEnergy(meta) && Number.isFinite(previousValue) && Number.isFinite(value) && value < previousValue;
	}

	function styleFor(uuid) {
		let hash = 0;
		for (const character of String(uuid)) hash = ((hash * 31) + character.charCodeAt(0)) >>> 0;
		return { color: PALETTE[hash % PALETTE.length], dash: DASHES[Math.floor(hash / PALETTE.length) % DASHES.length] };
	}

	function balanceText(balance, tolerance, labels, format) {
		if (!Number.isFinite(balance)) return labels.unavailable;
		if (Math.abs(balance) <= tolerance) return labels.balanced;
		return (balance > 0 ? labels.moreImport : labels.moreExport).replace("{value}", format(Math.abs(balance)));
	}

	return {
		STORAGE_KEY, POLL_INTERVAL, GAP_INTERVAL,
		numericTimestamp, scaledValue, category, isPower, isEnergy, chartValue,
		chooseEnergyChannel, choosePowerChannels, defaultSelection, cleanPreferences,
		limitSelection, hasReadingGap, isCounterReset, styleFor, balanceText
	};
}));

(function () {
	"use strict";
	if (typeof window === "undefined" || typeof document === "undefined") return;
	const Live = window.SmartMeterLive;
	const i18n = document.getElementById("i18n").dataset;
	const locale = i18n.locale === "de" ? "de-DE" : "en-US";
	const languageQuery = "&lang=" + encodeURIComponent(i18n.locale);
	let metadataVersion = "";
	let metadata = { channels: {} };
	let channels = [];
	let selected = new Set();
	let energyMode = "since-open";
	let backgroundCollection = false;
	let currentData = null;
	let timer = null;
	let stopped = false;
	let refreshing = false;
	let chart = null;
	let focusedDataset = -1;
	const histories = new Map();
	const lastTuple = new Map();
	const energySegments = new Map();

	function esc(value) { return String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c])); }
	function readableName(value) { return String(value || i18n.unnamed).replace(/_/g, " "); }
	function formatNumber(value, digits) { return new Intl.NumberFormat(locale, { maximumFractionDigits: digits === undefined ? 6 : digits, useGrouping: false }).format(value); }
	function channelUuid(channel) { return String(channel.uuid || channel.id || "").toLowerCase(); }
	function channelNumber(meta, index) { return Number.isInteger(meta.channel_index) ? meta.channel_index : index; }
	function channelName(item) {
		const catalog = i18n.locale === "de" ? item.meta.catalog_name_de : item.meta.catalog_name_en;
		return item.meta.display_name || catalog || readableName(item.meta.name || item.meta.identifier || item.uuid);
	}
	function displayValue(value, meta) {
		const scaled = Live.scaledValue(value, meta);
		const unit = String(meta.unit || "");
		if (scaled === null) return esc(value) + (unit ? " " + esc(unit) : "");
		const title = Number(meta.display_factor ?? 1) !== 1 ? ' title="' + esc(i18n.rawValue) + ": " + esc(value) + '"' : "";
		return "<span" + title + ">" + esc(formatNumber(scaled)) + (unit ? " " + esc(unit) : "") + "</span>";
	}
	function timestampText(value) {
		const milliseconds = Live.numericTimestamp(value);
		if (milliseconds === null) return esc(value);
		const date = new Date(milliseconds);
		const readable = Number.isNaN(date.getTime()) ? i18n.invalidTime : date.toLocaleString(locale, { dateStyle: "medium", timeStyle: "medium" });
		return '<span class="raw-time">' + esc(value) + "</span> (" + esc(readable) + ")";
	}

	async function loadMetadata() {
		const response = await fetch("?meta=1" + languageQuery, { cache: "no-store" });
		if (!response.ok) throw new Error(i18n.metadataFailed);
		metadata = await response.json();
		metadata.channels = metadata.channels || {};
		metadataVersion = String(metadata.version || "");
		channels = Object.keys(metadata.channels).map(uuid => ({ uuid: uuid.toLowerCase(), meta: metadata.channels[uuid] })).sort((a, b) => channelNumber(a.meta, 0) - channelNumber(b.meta, 0));
		loadPreferences();
		renderControls();
	}

	function loadPreferences() {
		let parsed = null;
		try { parsed = JSON.parse(localStorage.getItem(Live.STORAGE_KEY) || "null"); } catch (_) { parsed = null; }
		const cleaned = Live.cleanPreferences(parsed, channels.map(item => item.uuid));
		if (cleaned && cleaned.channels.length) {
			selected = Live.limitSelection(channels, new Set(cleaned.channels), 2);
			energyMode = cleaned.energyMode;
			backgroundCollection = cleaned.backgroundCollection;
		} else {
			selected = Live.defaultSelection(channels);
			energyMode = "since-open";
			backgroundCollection = false;
		}
		savePreferences();
	}

	function savePreferences() {
		try { localStorage.setItem(Live.STORAGE_KEY, JSON.stringify({ schema: 1, channels: Array.from(selected), energyMode, backgroundCollection })); } catch (_) { /* Browser storage may be unavailable. */ }
	}

	function renderControls() {
		const groups = new Map();
		channels.forEach(item => {
			const serial = String(item.meta.serial || "unknown");
			if (!groups.has(serial)) groups.set(serial, []);
			groups.get(serial).push(item);
		});
		const output = [];
		groups.forEach((items, serial) => {
			output.push('<fieldset><legend>' + esc(items[0].meta.head_name || serial) + '</legend><div class="channel-choices">');
			items.forEach(item => {
				output.push('<label><input type="checkbox" data-channel="' + esc(item.uuid) + '"' + (selected.has(item.uuid) ? " checked" : "") + '><span>' + esc(i18n.channel) + " " + esc(channelNumber(item.meta, 0)) + " – " + esc(channelName(item)) + '</span><small>' + esc(item.meta.unit || "—") + "</small></label>");
			});
			output.push("</div></fieldset>");
		});
		document.getElementById("channel-choices").innerHTML = output.join("");
		document.getElementById("energy-mode").value = energyMode;
		document.getElementById("background-collection").checked = backgroundCollection;
		document.querySelectorAll("input[data-channel]").forEach(input => input.addEventListener("change", changeSelection));
	}

	function changeSelection(event) {
		const uuid = event.currentTarget.dataset.channel;
		if (event.currentTarget.checked) {
			const candidate = metadata.channels[uuid] || {};
			const units = new Set(Array.from(selected).map(id => String((metadata.channels[id] || {}).unit || "")));
			units.add(String(candidate.unit || ""));
			if (units.size > 2) {
				event.currentTarget.checked = false;
				showChoiceMessage(i18n.maxUnits, true);
				return;
			}
			selected.add(uuid);
		} else selected.delete(uuid);
		if (!selected.size) {
			event.currentTarget.checked = true;
			selected.add(uuid);
			showChoiceMessage(i18n.oneChannel, true);
			return;
		}
		showChoiceMessage("", false);
		savePreferences();
		updateChart();
	}

	function showChoiceMessage(message, error) {
		const element = document.getElementById("chart-choice-message");
		element.textContent = message;
		element.className = error ? "status error" : "status";
	}

	function resetDefaults() {
		selected = Live.defaultSelection(channels);
		energyMode = "since-open";
		backgroundCollection = false;
		savePreferences();
		renderControls();
		showChoiceMessage("", false);
		updateChart();
	}

	function registerEnergyReset(serial, timestamp, resetUuid, newValue) {
		const segments = energySegments.get(serial) || [];
		if (segments.length && segments[segments.length - 1].start === timestamp) return;
		const bases = {};
		channels.filter(item => String(item.meta.serial || "unknown") === serial && Live.isEnergy(item.meta)).forEach(item => {
			const history = histories.get(item.uuid) || [];
			const latest = history.slice().reverse().find(point => point.y !== null && point.x <= timestamp);
			if (latest) bases[item.uuid] = latest.absolute;
		});
		bases[resetUuid] = newValue;
		segments.push({ start: timestamp, bases, reset: true });
		energySegments.set(serial, segments);
	}

	function energyRelative(uuid, point, meta) {
		const serial = String(meta.serial || "unknown");
		let segments = energySegments.get(serial);
		if (!segments || !segments.length) {
			segments = [{ start: point.x, bases: { [uuid]: point.absolute }, reset: false }];
			energySegments.set(serial, segments);
		}
		let segment = segments[0];
		for (const candidate of segments) if (candidate.start <= point.x) segment = candidate;
		if (segment.bases[uuid] === undefined) segment.bases[uuid] = point.absolute;
		return point.absolute - segment.bases[uuid];
	}

	function ingest(data) {
		const liveChannels = Array.isArray(data && data.data) ? data.data : (Array.isArray(data) ? data : []);
		liveChannels.forEach((channel, index) => {
			const uuid = channelUuid(channel);
			const meta = metadata.channels[uuid] || {};
			const tuples = Array.isArray(channel.tuples) ? channel.tuples : [];
			tuples.forEach(tuple => {
				if (!Array.isArray(tuple)) return;
				const x = Live.numericTimestamp(tuple[0]);
				const y = Live.scaledValue(tuple[1], meta);
				if (x === null || y === null) return;
				const key = String(tuple[0]) + "|" + String(tuple[1]);
				if (lastTuple.get(uuid) === key) return;
				const history = histories.get(uuid) || [];
				const previous = history.slice().reverse().find(point => point.y !== null);
				if (previous && x < previous.x) return;
				if (Live.isEnergy(meta) && !energySegments.has(String(meta.serial || "unknown"))) energySegments.set(String(meta.serial || "unknown"), [{ start: x, bases: { [uuid]: y }, reset: false }]);
				if (previous && Live.hasReadingGap(previous.x, x)) history.push({ x: previous.x + 1, y: null, absolute: null, raw: null });
				if (previous && Live.isCounterReset(meta, previous.absolute, y)) registerEnergyReset(String(meta.serial || "unknown"), x, uuid, y);
				history.push({ x, y, absolute: y, raw: tuple[1] });
				histories.set(uuid, history);
				lastTuple.set(uuid, key);
			});
		});
	}

	function renderTable(data) {
		if (data && data.error) throw new Error(data.error);
		const liveChannels = Array.isArray(data && data.data) ? data.data : (Array.isArray(data) ? data : []);
		if (!liveChannels.length) { document.getElementById("state").innerHTML = '<div class="empty">' + esc(i18n.noChannels) + "</div>"; return; }
		const groups = new Map();
		liveChannels.forEach((channel, index) => {
			const uuid = channelUuid(channel), meta = metadata.channels[uuid] || {}, serial = meta.serial || "unknown";
			if (!groups.has(serial)) groups.set(serial, { name: meta.head_name || serial, serial, channels: [] });
			groups.get(serial).channels.push({ channel, meta, index, uuid });
		});
		const output = [];
		groups.forEach(group => {
			output.push("<section><h2>" + esc(group.name) + '<span class="serial">' + esc(i18n.readingHead) + ": " + esc(group.serial) + "</span></h2>");
			output.push('<div class="table-wrap"><table><thead><tr><th class="time">' + esc(i18n.timestamp) + "</th><th>" + esc(i18n.value) + "</th></tr></thead><tbody>");
			group.channels.sort((a,b) => channelNumber(a.meta,a.index)-channelNumber(b.meta,b.index)).forEach(item => {
				const number = channelNumber(item.meta,item.index), identifier = item.meta.identifier || item.channel.identifier || "";
				output.push('<tr class="channel-heading"><th colspan="2"><span class="channel-title">' + esc(i18n.channel) + " " + esc(number) + " - " + esc(channelName(item)) + '</span><span class="channel-meta">OBIS: ' + esc(identifier || "-") + " | UUID: " + esc(item.uuid || "-") + "</span></th></tr>");
				const tuples = Array.isArray(item.channel.tuples) ? item.channel.tuples : [];
				if (!tuples.length) output.push('<tr><td colspan="2" class="empty">' + esc(i18n.noReading) + "</td></tr>");
				else tuples.forEach(tuple => output.push("<tr><td>" + timestampText(Array.isArray(tuple) ? tuple[0] : "") + '</td><td class="value">' + displayValue(Array.isArray(tuple) ? tuple[1] : tuple, item.meta) + "</td></tr>"));
			});
			output.push("</tbody></table></div></section>");
		});
		output.push('<p class="status">vzLogger ' + esc(data.version || "") + (data.generator ? " | " + esc(data.generator) : "") + "</p>");
		document.getElementById("state").innerHTML = output.join("");
	}

	function datasetFor(item) {
		const history = histories.get(item.uuid) || [], meta = item.meta, style = Live.styleFor(item.uuid);
		const points = [];
		const resetStarts = (energySegments.get(String(meta.serial || "unknown")) || []).filter(segment => segment.reset).map(segment => segment.start);
		let previousX = null;
		history.forEach(point => {
			if (Live.isEnergy(meta) && resetStarts.some(start => previousX !== null && previousX < start && point.x >= start)) points.push({ x: point.x - 1, y: null, absolute: null });
			points.push({
				x: point.x,
				y: point.y === null ? null : (Live.isEnergy(meta) && energyMode === "since-open" ? energyRelative(item.uuid, point, meta) : Live.chartValue(point.y, meta)),
				absolute: point.absolute
			});
			previousX = point.x;
		});
		return {
			label: (meta.head_name ? meta.head_name + " – " : "") + channelName(item),
			data: points,
			yAxisID: "unit-" + String(meta.unit || "value"), borderColor: colorWithAlpha(style.color, 0.82), backgroundColor: colorWithAlpha(style.color, 0.82),
			borderDash: style.dash, borderWidth: 2, pointRadius: 0, pointHoverRadius: 4, spanGaps: false,
			cubicInterpolationMode: "monotone", tension: 0.15, metaInfo: meta, uuid: item.uuid, order: 0
		};
	}

	function updateChart() {
		if (typeof Chart === "undefined") return;
		const items = channels.filter(item => selected.has(item.uuid));
		const datasets = items.map(datasetFor);
		const units = [];
		datasets.forEach(dataset => { const unit = String(dataset.metaInfo.unit || ""); if (!units.includes(unit)) units.push(unit); });
		const scales = { x: { type: "linear", title: { display: true, text: i18n.timeAxis }, ticks: { callback: value => new Date(value).toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit", second: "2-digit" }), maxRotation: 0 } } };
		units.forEach((unit, index) => {
			const unitDatasets = datasets.filter(dataset => String(dataset.metaInfo.unit || "") === unit);
			const power = unitDatasets.some(dataset => Live.isPower(dataset.metaInfo));
			const relativeEnergy = energyMode === "since-open" && unitDatasets.some(dataset => Live.isEnergy(dataset.metaInfo));
			scales["unit-" + (unit || "value")] = {
				type: "linear", position: index === 0 ? "left" : "right", beginAtZero: power || relativeEnergy,
				grace: power || relativeEnergy ? 0 : "5%",
				title: { display: true, text: unit || i18n.value }, grid: { drawOnChartArea: index === 0 },
				ticks: { callback: value => formatNumber(value) + (unit ? " " + unit : "") }
			};
		});
		const config = {
			type: "line", data: { datasets }, options: {
				responsive: true, maintainAspectRatio: false, animation: false, normalized: true, parsing: false,
				interaction: { mode: "index", intersect: false }, scales,
				plugins: {
					decimation: { enabled: true, algorithm: "min-max" },
					legend: { position: "bottom", labels: { usePointStyle: true }, onClick: (_event, legendItem) => focusDataset(legendItem.datasetIndex) },
					tooltip: { callbacks: { label: context => {
						const dataset = context.dataset, unit = dataset.metaInfo.unit || "", point = dataset.data[context.dataIndex];
						let text = dataset.label + ": " + formatNumber(context.parsed.y) + (unit ? " " + unit : "");
						if (energyMode === "since-open" && Live.isEnergy(dataset.metaInfo) && point && Number.isFinite(point.absolute)) text += " (" + i18n.absolute + ": " + formatNumber(point.absolute) + (unit ? " " + unit : "") + ")";
						return text;
					} } }
				},
				onHover: (_event, active) => focusDataset(active.length ? active[0].datasetIndex : -1)
			}
		};
		if (chart) {
			chart.data.datasets = datasets;
			chart.options.scales = scales;
			chart.update("none");
		} else chart = new Chart(document.getElementById("live-chart"), config);
		focusedDataset = -1;
		renderSummary();
	}

	function focusDataset(index) {
		if (!chart || focusedDataset === index) return;
		focusedDataset = index;
		chart.data.datasets.forEach((dataset, datasetIndex) => {
			const style = Live.styleFor(dataset.uuid);
			dataset.borderColor = colorWithAlpha(style.color, index < 0 || datasetIndex === index ? 0.82 : 0.3);
			dataset.borderWidth = datasetIndex === index ? 3.5 : 2;
			dataset.order = datasetIndex === index ? -1 : 0;
		});
		chart.update("none");
	}

	function colorWithAlpha(hex, alpha) {
		const value = hex.replace("#", "");
		return "rgba(" + parseInt(value.slice(0,2),16) + "," + parseInt(value.slice(2,4),16) + "," + parseInt(value.slice(4,6),16) + "," + alpha + ")";
	}

	function latestPoint(uuid) { return (histories.get(uuid) || []).slice().reverse().find(point => point.y !== null) || null; }
	function firstPointSince(uuid, timestamp) { return (histories.get(uuid) || []).find(point => point.y !== null && point.x >= timestamp) || null; }

	function renderSummary() {
		const groups = new Map();
		channels.forEach(item => { const serial = String(item.meta.serial || "unknown"); if (!groups.has(serial)) groups.set(serial, []); groups.get(serial).push(item); });
		const output = [];
		groups.forEach((items, serial) => {
			if (!items.some(item => Live.isEnergy(item.meta) || Live.isPower(item.meta))) return;
			const imported = Live.chooseEnergyChannel(items, "import"), exported = Live.chooseEnergyChannel(items, "export");
			const segments = energySegments.get(serial) || [];
			const latestSegment = segments.length ? segments[segments.length - 1] : null;
			const start = latestSegment && latestSegment.reset ? latestSegment.start : 0;
			function delta(item) { if (!item) return null; const first = firstPointSince(item.uuid, start), last = latestPoint(item.uuid); return first && last ? Math.max(0, last.absolute - first.absolute) : null; }
			const importDelta = delta(imported), exportDelta = delta(exported);
			const powerItems = Live.choosePowerChannels(items), powerValues = [];
			powerItems.forEach(item => (histories.get(item.uuid) || []).forEach(point => { if (point.y !== null) powerValues.push({ value: Live.chartValue(point.y, item.meta), x: point.x }); }));
			const latestPowers = powerItems.map(item => ({ item, point: latestPoint(item.uuid) })).filter(entry => entry.point);
			let currentPower = null;
			if (latestPowers.length === 1 && Live.category(latestPowers[0].item.meta) === "active_power_total") currentPower = latestPowers[0].point.y;
			else if (latestPowers.length) currentPower = latestPowers.reduce((sum, entry) => sum + Live.chartValue(entry.point.y, entry.item.meta), 0);
			const importPeak = powerValues.filter(point => point.value >= 0).sort((a,b) => b.value-a.value)[0];
			const exportPeak = powerValues.filter(point => point.value < 0).sort((a,b) => a.value-b.value)[0];
			const unit = imported && imported.meta.unit || exported && exported.meta.unit || "kWh";
			const balance = Number.isFinite(importDelta) && Number.isFinite(exportDelta) ? importDelta - exportDelta : NaN;
			const balanceSentence = Live.balanceText(balance, 0.001, { unavailable:i18n.unavailable, balanced:i18n.balanceEqual, moreImport:i18n.balanceImport, moreExport:i18n.balanceExport }, value => formatNumber(value, 3) + " " + unit);
			output.push('<section class="summary-reader"><h3>' + esc(items[0].meta.head_name || serial) + (start ? ' <small>' + esc(i18n.sinceRebaseline) + "</small>" : "") + '</h3><div class="summary-grid">');
			output.push(summaryCard(i18n.sessionImport, importDelta, unit));
			output.push(summaryCard(i18n.sessionExport, exportDelta, unit));
			output.push('<div class="summary-card"><span>' + esc(i18n.sessionBalance) + '</span><strong>' + esc(balanceSentence) + "</strong></div>");
			const direction = currentPower === null ? i18n.unavailable : (Math.abs(currentPower) < 0.001 ? i18n.balanceEqual : (currentPower > 0 ? i18n.currentImport : i18n.currentExport).replace("{value}", formatNumber(Math.abs(currentPower), 1) + " W"));
			output.push('<div class="summary-card"><span>' + esc(i18n.currentFlow) + '</span><strong>' + esc(direction) + "</strong></div>");
			output.push(peakCard(i18n.peakImport, importPeak)); output.push(peakCard(i18n.peakExport, exportPeak));
			output.push("</div></section>");
		});
		document.getElementById("session-summary").innerHTML = output.join("");
	}

	function summaryCard(label, value, unit) { return '<div class="summary-card"><span>' + esc(label) + '</span><strong>' + (Number.isFinite(value) ? esc(formatNumber(value, 6) + " " + unit) : esc(i18n.unavailable)) + "</strong></div>"; }
	function peakCard(label, peak) { return '<div class="summary-card"><span>' + esc(label) + '</span><strong>' + (peak ? esc(formatNumber(Math.abs(peak.value), 1) + " W") + '<small>' + esc(new Date(peak.x).toLocaleTimeString(locale)) + "</small>" : esc(i18n.unavailable)) + "</strong></div>"; }

	async function refresh() {
		if (stopped || refreshing) return;
		refreshing = true;
		try {
			const response = await fetch("?json=1" + languageQuery, { cache: "no-store" });
			if (!response.ok) throw new Error(i18n.dataFailed);
			const version = response.headers.get("X-Smartmeter-Metadata-Version") || "";
			if (version && version !== metadataVersion) await loadMetadata();
			const data = await response.json();
			if (data && data.error) throw new Error(data.error);
			currentData = data; ingest(data);
			if (!document.hidden) {
				renderTable(data); updateChart();
				document.getElementById("status").className = "status";
				document.getElementById("status").textContent = i18n.lastUpdate + ": " + new Date().toLocaleString(locale);
			}
		} catch (error) {
			if (!document.hidden) {
				document.getElementById("status").className = "status error";
				document.getElementById("status").textContent = error.message;
			}
		} finally { refreshing = false; schedule(); }
	}

	function schedule(immediate) {
		clearTimeout(timer);
		if (stopped || (document.hidden && !backgroundCollection)) return;
		timer = setTimeout(refresh, immediate ? 0 : Live.POLL_INTERVAL);
	}

	document.addEventListener("visibilitychange", () => {
		if (document.hidden && !backgroundCollection) { clearTimeout(timer); return; }
		if (!document.hidden && currentData) { renderTable(currentData); updateChart(); }
		schedule(true);
	});
	document.getElementById("energy-mode").addEventListener("change", event => { energyMode = event.target.value === "absolute" ? "absolute" : "since-open"; savePreferences(); updateChart(); });
	document.getElementById("background-collection").addEventListener("change", event => { backgroundCollection = event.target.checked; savePreferences(); schedule(true); });
	document.getElementById("reset-chart-defaults").addEventListener("click", resetDefaults);
	window.addEventListener("beforeunload", () => { stopped = true; clearTimeout(timer); });

	(async function initialize() {
		try { await loadMetadata(); await refresh(); }
		catch (error) { document.getElementById("status").className = "status error"; document.getElementById("status").textContent = error.message; }
	}());
}());
