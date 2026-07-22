"use strict";

const assert = require("node:assert/strict");
const Live = require("../webfrontend/htmlauth/vzlogger_live.js");

assert.equal(Live.numericTimestamp(1700000000), 1700000000000, "epoch seconds become milliseconds");
assert.equal(Live.numericTimestamp(1700000000123), 1700000000123, "epoch milliseconds stay unchanged");
assert.equal(Live.scaledValue(12345, { display_factor: 0.001 }), 12.345, "display scaling is applied");
assert.equal(Live.chartValue(500, { category: "active_power_import" }), 500, "grid import is positive");
assert.equal(Live.chartValue(500, { category: "active_power_export" }), -500, "grid export is negative");
assert.equal(Live.chartValue(-500, { category: "active_power_total" }), -500, "signed total power is retained");

const channels = [
	{ uuid: "total", meta: { serial: "reader", channel_index: 0, unit: "W", category: "active_power_total", identifier: "1-0:16.7.0" } },
	{ uuid: "import", meta: { serial: "reader", channel_index: 1, unit: "kWh", category: "active_energy_import", identifier: "1-0:1.8.0" } },
	{ uuid: "export", meta: { serial: "reader", channel_index: 2, unit: "kWh", category: "active_energy_export", identifier: "1-0:2.8.0" } },
	{ uuid: "tariff", meta: { serial: "reader", channel_index: 3, unit: "kWh", category: "active_energy_import", identifier: "1-0:1.8.1" } },
	{ uuid: "voltage", meta: { serial: "reader", channel_index: 4, unit: "V", category: "voltage", identifier: "1-0:32.7.0" } }
];
assert.deepEqual(Array.from(Live.defaultSelection(channels)).sort(), ["export", "import", "total"], "defaults select total power and total energy only");
assert.equal(Live.chooseEnergyChannel(channels, "import").uuid, "import", "canonical total import is selected");

const ambiguous = channels.concat({ uuid: "import-copy", meta: { serial: "reader", unit: "kWh", category: "active_energy_import", identifier: "1-0:1.8.0" } });
assert.equal(Live.chooseEnergyChannel(ambiguous, "import"), null, "ambiguous counters are not guessed");

assert.deepEqual(Live.cleanPreferences({ schema: 1, channels: ["TOTAL", "missing"], energyMode: "absolute", backgroundCollection: true }, ["total"]), {
	schema: 1, channels: ["total"], energyMode: "absolute", backgroundCollection: true
}, "preferences are normalized and unavailable UUIDs are removed");
assert.equal(Live.cleanPreferences({ schema: 2, channels: [] }, []), null, "unknown preference schemas fall back to defaults");
assert.deepEqual(Array.from(Live.limitSelection(channels, new Set(["total", "import", "voltage"]), 2)), ["total", "import"], "restored preferences are limited to two unit groups");
assert.equal(Live.hasReadingGap(1000, 1000 + Live.GAP_INTERVAL + 1), true, "a delayed reading creates a chart gap");
assert.equal(Live.hasReadingGap(1000, 1000 + Live.GAP_INTERVAL), false, "the accepted polling window remains connected");
assert.equal(Live.isCounterReset({ category: "active_energy_export" }, 20, 19), true, "a decreasing energy counter starts a new baseline");
assert.equal(Live.isCounterReset({ category: "active_power_total" }, 20, 19), false, "ordinary power changes are not counter resets");

const labels = { unavailable: "n/a", balanced: "balanced", moreImport: "import {value}", moreExport: "export {value}" };
assert.equal(Live.balanceText(0.0009, 0.001, labels, String), "balanced", "one Wh balance tolerance is applied");
assert.equal(Live.balanceText(0.25, 0.001, labels, String), "import 0.25", "positive balance means grid import");
assert.equal(Live.balanceText(-0.25, 0.001, labels, String), "export 0.25", "negative balance means grid export");

console.log("vzLogger live chart model tests passed");
