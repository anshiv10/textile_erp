/* ══════════════════════════════════════════════════════════════════════════════
   Textile ERP report look - KPI cards, Download (Excel / PDF), Date Presets,
   Clear Filters. The same block is in party_outstanding.js and
   textile_business_summary.js (report scripts cannot share files); keep both
   copies identical and bump VERSION when changing it.
   Uses only what ships with Frappe (export_report) - no CDN.
   ══════════════════════════════════════════════════════════════════════════════ */
frappe.provide("textile_erp");
(function () {
	const VERSION = 1;
	if (textile_erp.report_ui && textile_erp.report_ui.version >= VERSION) return;

	const ACCENT = {
		Blue: "#2563eb", Green: "#16a34a", Orange: "#d97706", Red: "#dc2626",
		Grey: "#475569", Gray: "#475569", Purple: "#7c3aed", Cyan: "#0891b2",
	};
	const ui = { version: VERSION };

	ui.styles = function () {
		if (document.getElementById("tx-report-ui-styles")) return;
		const s = document.createElement("style");
		s.id = "tx-report-ui-styles";
		s.textContent = `
			.tx-kpi-wrap { padding: 4px 0 6px; margin-bottom: 8px; }
			.tx-kpi-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; padding: 10px 2px 6px; }
			@media (max-width: 991px) { .tx-kpi-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
			.tx-kpi-card { background: var(--card-bg, #fff); border: 1px solid var(--border-color, #d1d8dd); border-radius: 12px;
				padding: 18px 14px 16px; text-align: center; position: relative; overflow: hidden;
				box-shadow: 0 1px 4px rgba(0,0,0,.06); transition: transform .18s ease, box-shadow .18s ease; }
			.tx-kpi-card::before { content: ""; position: absolute; top: 0; left: 0; right: 0; height: 4px;
				background: var(--tx-accent, #2490ef); }
			.tx-kpi-card:hover { transform: translateY(-3px); box-shadow: 0 6px 18px rgba(0,0,0,.12); }
			.tx-kpi-icon { font-size: 18px; line-height: 1; margin: 2px 0 6px; }
			.tx-kpi-val { font-size: 19px; font-weight: 700; line-height: 1.2; margin-bottom: 6px; color: var(--tx-accent); }
			.tx-kpi-lbl { font-size: 10px; font-weight: 600; color: var(--text-muted, #6c757d); text-transform: uppercase;
				letter-spacing: .5px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
			.tx-kpi-empty { padding: 14px; text-align: center; color: var(--text-muted, #94a3b8); font-size: 13px; }
		`;
		document.head.appendChild(s);
	};

	ui.fmt = function (value, datatype, currency) {
		value = flt(value);
		if (datatype === "Int") return format_number(value, null, 0);
		if (datatype === "Float") return format_number(value, null, 2);
		if (datatype === "Percent") return format_number(value, null, 2) + "%";
		return format_currency(value, currency || frappe.defaults.get_default("currency"));
	};

	ui.panel = function (report) {
		let $wrap = report.page.main.find(".tx-kpi-wrap");
		if (!$wrap.length) {
			$wrap = $('<div class="tx-kpi-wrap"></div>');
			const $form = report.page.main.find(".page-form").first();
			if ($form.length) $wrap.insertBefore($form);
			else $wrap.prependTo(report.page.main);
		}
		return $wrap;
	};

	ui.draw = function (report) {
		ui.styles();
		const $wrap = ui.panel(report);
		const cards = report.__tx_summary || [];
		if (!cards.length) {
			$wrap.html(`<div class="tx-kpi-empty">${__("No data for these filters")}</div>`);
			return;
		}
		const icon = (report.__tx_cfg && report.__tx_cfg.icon) || (() => "📊");
		$wrap.html(`<div class="tx-kpi-grid">${cards.map((c) => `
			<div class="tx-kpi-card" style="--tx-accent:${ACCENT[c.indicator] || ACCENT.Blue}">
				<div class="tx-kpi-icon">${icon(c)}</div>
				<div class="tx-kpi-val" data-count="${c.datatype === "Int" ? cint(c.value) : ""}">${ui.fmt(c.value, c.datatype, c.currency)}</div>
				<div class="tx-kpi-lbl">${frappe.utils.escape_html(c.label || "")}</div>
			</div>`).join("")}</div>`);
		$wrap.find(".tx-kpi-val[data-count]").each(function () {
			const target = cint(this.dataset.count);
			if (target > 0) ui.count_up(this, target);
		});
	};

	ui.count_up = function (el, target) {
		let cur = 0;
		const step = Math.max(1, Math.ceil(target / 40));
		const t = setInterval(() => {
			cur = Math.min(target, cur + step);
			el.textContent = format_number(cur, null, 0);
			if (cur >= target) clearInterval(t);
		}, 30);
	};

	/* set several filters, then refresh once */
	ui.apply = function (report, values) {
		report._no_refresh = true;
		const jobs = Object.keys(values).map((k) => () => {
			const f = report.get_filter(k);
			return f ? f.set_value(values[k]) : null;
		});
		return frappe.run_serially([
			...jobs,
			() => frappe.timeout(0.2),
			() => {
				report._no_refresh = false;
				report.refresh();
			},
		]);
	};

	/* Indian financial year (April - March) */
	ui.fy = function (offset = 0) {
		const today = frappe.datetime.str_to_obj(frappe.datetime.get_today());
		const y = (today.getMonth() >= 3 ? today.getFullYear() : today.getFullYear() - 1) + offset;
		return { start: `${y}-04-01`, end: `${y + 1}-03-31` };
	};

	ui.setup = function (report, cfg) {
		report.__tx_cfg = cfg;
		ui.styles();
		// Frappe's plain summary strip is replaced by the card panel
		report.render_summary = function (summary) {
			report.__tx_summary = summary || [];
			report.$summary && report.$summary.hide();
			ui.draw(report);
		};
		const download = __("⬇ Download");
		report.page.add_inner_button(__("Excel"), () => report.export_report(), download);
		report.page.add_inner_button(__("PDF"), () => ui.pdf(report), download);
		(cfg.presets ? cfg.presets() : []).forEach((p) =>
			report.page.add_inner_button(p.label, () => ui.apply(report, p.values), __("📅 Date Presets"))
		);
		report.page.add_inner_button(__("✕ Clear Filters"), () => ui.apply(report, cfg.defaults()));
	};

	/* ── PDF: a printable page (landscape) - use "Save as PDF" in the print window ── */
	ui.pdf = function (report) {
		const rows = report.data || [];
		if (!rows.length) {
			frappe.msgprint({ title: __("No Data"), message: __("Run the report first."), indicator: "orange" });
			return;
		}
		const esc = frappe.utils.escape_html;
		const text = (html) => $("<div>").html(html == null ? "" : String(html)).text().trim();
		const cols = (report.columns || []).filter((c) => !c.hidden);
		const filters = report.get_filter_values() || {};
		const applied = (report.filters || [])
			.filter((f) => f.df && filters[f.df.fieldname] && f.df.fieldname !== "company" && !(Array.isArray(filters[f.df.fieldname]) && !filters[f.df.fieldname].length))
			.map((f) => `${esc(__(f.df.label))}: ${esc([].concat(filters[f.df.fieldname]).map((v) => (f.df.fieldtype === "Date" ? frappe.datetime.str_to_user(v) : v)).join(", "))}`);
		const cards = (report.__tx_summary || []).map((c) =>
			`<div class="c" style="border-top:4px solid ${ACCENT[c.indicator] || ACCENT.Blue}"><b style="color:${ACCENT[c.indicator] || ACCENT.Blue}">${
				esc(ui.fmt(c.value, c.datatype, c.currency))}</b><span>${esc(c.label)}</span></div>`
		).join("");
		const numeric = (c) => ["Currency", "Float", "Int", "Percent"].includes(c.fieldtype);
		const body = rows.map((r) => `<tr class="${r.bold ? "b" : ""}">${cols.map((c, ci) => {
			const value = r[c.fieldname];
			const shown = value == null || value === "" ? "" : text(frappe.format(value, c, { inline: true }, r));
			const pad = ci === 0 && r.indent ? ' style="padding-left:18px"' : "";
			return `<td class="${numeric(c) ? "n" : ""}"${pad}>${esc(shown)}</td>`;
		}).join("")}</tr>`).join("");
		const title = __(report.report_name);
		const html = `<!DOCTYPE html><html><head><meta charset="utf-8"><title>${esc(title)}</title><style>
			body{font-family:Arial,sans-serif;font-size:9.5px;margin:18px 22px;color:#1e293b}
			h1{font-size:15px;margin:0 0 3px;color:#1e3a5f}.m{font-size:9px;color:#64748b;margin-bottom:10px}
			.cards{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:12px}
			.c{border:1px solid #e2e8f0;border-radius:6px;padding:7px;text-align:center}.c b{display:block;font-size:12px}
			.c span{font-size:8px;color:#64748b;text-transform:uppercase}
			table{width:100%;border-collapse:collapse}th{background:#1e3a5f;color:#fff;padding:5px 6px;font-size:9px;text-align:left;border:1px solid #2563eb}
			td{padding:4px 6px;border:1px solid #e2e8f0;vertical-align:top}td.n{text-align:right;white-space:nowrap}
			tr:nth-child(even) td{background:#f8fafc}tr.b td{font-weight:700;background:#eef2ff}
			.f{margin-top:10px;font-size:8.5px;color:#94a3b8;text-align:right}
			@page{size:A4 landscape;margin:12mm 10mm}@media print{body{margin:0}thead{display:table-header-group}tr{page-break-inside:avoid}}
			</style></head><body><h1>${esc(title)}</h1>
			<div class="m">${esc(filters.company || "")} &nbsp;|&nbsp; ${esc(__("Generated"))}: ${esc(frappe.datetime.str_to_user(frappe.datetime.now_datetime()))}${
				applied.length ? " &nbsp;|&nbsp; " + applied.join(" &nbsp;|&nbsp; ") : ""}</div>
			${cards ? `<div class="cards">${cards}</div>` : ""}
			<table><thead><tr>${cols.map((c) => `<th>${esc(__(c.label || c.fieldname))}</th>`).join("")}</tr></thead><tbody>${body}</tbody></table>
			<div class="f">${esc(title)}</div>
			<script>window.onload=function(){setTimeout(function(){window.print();},400);};<\/script></body></html>`;
		const win = window.open("", "_blank");
		if (!win) {
			frappe.msgprint({ title: __("Popup Blocked"), message: __("Allow popups for this site, then click PDF again."), indicator: "orange" });
			return;
		}
		win.document.open();
		win.document.write(html);
		win.document.close();
	};

	textile_erp.report_ui = ui;
})();

const TX_TBS_ICONS = ["📦", "🧾", "💳", "🏦", "🛒", "📈"];

frappe.query_reports["Textile Business Summary"] = {
	filters: [
		{ fieldname: "company", label: __("Company"), fieldtype: "Link", options: "Company", reqd: 1,
		  default: frappe.defaults.get_user_default("Company") },
		{ fieldname: "from_date", label: __("From Date"), fieldtype: "Date", reqd: 1, default: textile_erp.report_ui.fy(0).start },
		{ fieldname: "to_date", label: __("To Date"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
		{ fieldname: "report_date", label: __("Outstanding / Bank as on"), fieldtype: "Date", reqd: 1, default: frappe.datetime.get_today() },
	],

	onload(report) {
		const ui = textile_erp.report_ui;
		const today = frappe.datetime.get_today();
		const upto = (d) => (d > today ? today : d);
		const period = (label, from, to) => ({ label, values: { from_date: from, to_date: to, report_date: upto(to) } });
		const last_month = frappe.datetime.add_months(today, -1);
		const q_start = frappe.datetime.month_start(frappe.datetime.add_months(today, -(frappe.datetime.str_to_obj(today).getMonth() % 3)));
		ui.setup(report, {
			icon: (c) => TX_TBS_ICONS[(report.__tx_summary || []).indexOf(c)] || "📊",
			presets: () => [
				period(__("This Month"), frappe.datetime.month_start(today), today),
				period(__("Last Month"), frappe.datetime.month_start(last_month), frappe.datetime.month_end(last_month)),
				period(__("This Quarter"), q_start, today),
				period(__("This FY"), ui.fy(0).start, today),
				period(__("Last FY"), ui.fy(-1).start, ui.fy(-1).end),
			],
			defaults: () => ({ from_date: ui.fy(0).start, to_date: today, report_date: today }),
		});
	},

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		if (column.fieldname === "amount" && !data.bold && flt(data.amount) < 0)
			value = `<span style="color:var(--red-600)">${value}</span>`;
		if (data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
