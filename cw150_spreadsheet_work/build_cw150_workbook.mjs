import fs from "node:fs/promises";
import { SpreadsheetFile, Workbook } from "@oai/artifact-tool";

const outputDir = "outputs/CW-150";
const previewDir = "cw150_spreadsheet_work/previews";
await fs.mkdir(outputDir, { recursive: true });
await fs.mkdir(previewDir, { recursive: true });

const wb = Workbook.create();
const navy = "#17365D";
const teal = "#0F6B78";
const blue = "#D9EAF7";
const light = "#F4F7FA";
const amber = "#FFF2CC";
const green = "#E2F0D9";
const red = "#FCE4D6";
const gray = "#667085";

function baseSheet(name, title, subtitle, cols) {
  const s = wb.worksheets.add(name);
  s.showGridLines = false;
  s.getRange(`A1:${cols}1`).merge();
  s.getRange("A1").values = [[title]];
  s.getRange(`A2:${cols}2`).merge();
  s.getRange("A2").values = [[subtitle]];
  s.getRange(`A1:${cols}1`).format = { fill: navy, font: { bold: true, color: "#FFFFFF", size: 16 }, rowHeight: 30 };
  s.getRange(`A2:${cols}2`).format = { fill: blue, font: { color: navy, italic: true }, wrapText: true, rowHeight: 32 };
  return s;
}

function header(range) {
  range.format = { fill: teal, font: { bold: true, color: "#FFFFFF" }, wrapText: true, rowHeight: 28, borders: { preset: "inside", style: "thin", color: "#B7C9D6" } };
}

function body(range) {
  range.format = { borders: { preset: "inside", style: "thin", color: "#D9E2E8" }, wrapText: true, verticalAlignment: "center" };
}

const summary = baseSheet("Summary", "CW-150 Migration, UAT & Cutover Control", "Formula-driven control sheet. No Production migration is authorized by this workbook.", "H");
summary.getRange("A4:B10").values = [
  ["Control KPI", "Value"],
  ["Migration objects", null],
  ["Objects accepted", null],
  ["Reconciliation failures", null],
  ["UAT scenarios passed", null],
  ["Open critical issues", null],
  ["Cutover gates complete", null],
];
summary.getRange("B5:B10").formulas = [
  ["=COUNTA('Migration Register'!$B$5:$B$32)"],
  ["=COUNTIF('Migration Register'!$L$5:$L$32,\"Accepted\")"],
  ["=COUNTIF('Reconciliation'!$G$5:$G$14,\"FAIL\")"],
  ["=COUNTIF('UAT Scenarios'!$H$5:$H$10,\"Passed\")"],
  ["=COUNTIFS('Issue Log'!$C$5:$C$34,\"Critical\",'Issue Log'!$H$5:$H$34,\"<>Closed\")"],
  ["=COUNTIF('Cutover Checklist'!$F$5:$F$20,\"Complete\")"],
];
header(summary.getRange("A4:B4")); body(summary.getRange("A5:B10"));
summary.getRange("B5:B10").format = { fill: light, font: { bold: true, color: navy, size: 14 }, numberFormat: "#,##0" };
summary.getRange("D4:H9").values = [
  ["Gate", "Owner", "Required evidence", "Status", "Decision date"],
  ["Data mapping approved", "Business owners", "Signed mapping + source extract", "Not Started", null],
  ["Dry run reconciled", "Migration Lead / Finance", "Import logs + reconciliation", "Not Started", null],
  ["Golden UAT signed", "Process owners", "Scenario evidence", "Not Started", null],
  ["Pilot / parallel run accepted", "Steering Committee", "Pilot sign-off", "Not Started", null],
  ["Production cutover approval", "Executive Sponsor", "Go / No-Go minutes", "Blocked", null],
];
header(summary.getRange("D4:H4")); body(summary.getRange("D5:H9"));
summary.getRange("G5:G9").dataValidation = { rule: { type: "list", values: ["Not Started", "In Progress", "Complete", "Blocked"] } };
summary.getRange("G5:G9").conditionalFormats.add("containsText", { text: "Complete", format: { fill: green, font: { color: "#375623", bold: true } } });
summary.getRange("G5:G9").conditionalFormats.add("containsText", { text: "Blocked", format: { fill: red, font: { color: "#9C0006", bold: true } } });
summary.getRange("H5:H9").format.numberFormat = "yyyy-mm-dd";
summary.getRange("A13:H17").values = [
  ["Operating rule", "Details", null, null, null, null, null, null],
  ["Environment", "All imports and module upgrades run on Development/Staging first.", null, null, null, null, null, null],
  ["Financial safety", "Do not post invoices, bills, journal entries, payments, taxes, or opening balances without explicit approval.", null, null, null, null, null, null],
  ["Data preservation", "Approved/posted documents are corrected by revision, reversal, cancellation, or credit note—not deletion.", null, null, null, null, null, null],
  ["Cutover", "Production remains blocked until dry run, reconciliation, role UAT, pilot, backup, and signed Go/No-Go are complete.", null, null, null, null, null, null],
];
summary.getRange("B13:H13").merge(); summary.getRange("B14:H14").merge(); summary.getRange("B15:H15").merge(); summary.getRange("B16:H16").merge(); summary.getRange("B17:H17").merge();
header(summary.getRange("A13:H13")); body(summary.getRange("A14:H17"));
summary.getRange("A:A").format.columnWidth = 25; summary.getRange("B:B").format.columnWidth = 18; summary.getRange("C:C").format.columnWidth = 3;
summary.getRange("D:D").format.columnWidth = 25; summary.getRange("E:E").format.columnWidth = 24; summary.getRange("F:F").format.columnWidth = 34; summary.getRange("G:G").format.columnWidth = 16; summary.getRange("H:H").format.columnWidth = 14;
summary.freezePanes.freezeRows(3);

const migrationObjects = [
  [1,"Companies","res.company"],[2,"Branches","res.company / branch configuration"],[3,"Users","res.users"],[4,"Partners","res.partner"],
  [5,"Product Categories","product.category"],[6,"Products / Resources","product.template"],[7,"Units of Measure","uom.uom"],[8,"Cost Codes","mu.construction.cost.code"],
  [9,"WBS Templates","mu.construction.wbs"],[10,"Locations / LBS","mu.construction.location"],[11,"Warehouses / Stock Locations","stock.warehouse / stock.location"],[12,"Equipment","maintenance.equipment / fleet.vehicle"],
  [13,"Contracts","mu.construction.contract"],[14,"Projects","project.project"],[15,"BOQs","mu.construction.boq / line"],[16,"Budget Baselines","mu.construction.budget.baseline / line"],
  [17,"Open Purchase Orders","purchase.order"],[18,"Open Subcontracts","purchase.order (subcontract)"],[19,"Inventory Balances","stock inventory adjustment"],[20,"Customer Advances","account.move / reconciliation"],
  [21,"Supplier / Subcontract Advances","account.move / reconciliation"],[22,"Retention Receivable","opening financial migration"],[23,"Retention Payable","opening financial migration"],[24,"Guarantees","mu.construction.guarantee"],
  [25,"Open IPCs","mu.construction.client.ipc"],[26,"Open Vendor Bills","account.move"],[27,"Opening Accounting Balances","account.move"],[28,"Documents","documents.document"],
];
const mr = baseSheet("Migration Register", "Migration Object Register", "Complete in dependency order. Status Accepted requires mapping, dry run, counts, reconciliation and owner sign-off.", "L");
mr.getRange("A4:L4").values = [["Seq","Object","Odoo model / route","Business owner","Source file / system","Mapping status","Dry-run status","Source rows","Imported rows","Rejected rows","Count variance","Acceptance"]];
mr.getRange("A5:L32").values = migrationObjects.map(([seq,obj,model]) => [seq,obj,model,"","","Not Started","Not Started",0,0,0,null,"Not Started"]);
mr.getRange("K5:K32").formulas = migrationObjects.map((_,i)=>[`=I${i+5}+J${i+5}-H${i+5}`]);
header(mr.getRange("A4:L4")); body(mr.getRange("A5:L32"));
mr.getRange("F5:G32").dataValidation = { rule: { type: "list", values: ["Not Started","In Progress","Ready","Blocked"] } };
mr.getRange("L5:L32").dataValidation = { rule: { type: "list", values: ["Not Started","Rejected","Accepted"] } };
mr.getRange("H5:K32").format.numberFormat = "#,##0";
mr.getRange("K5:K32").conditionalFormats.add("cellIs", { operator: "notEqual", formula: 0, format: { fill: red, font: { color: "#9C0006", bold: true } } });
mr.getRange("L5:L32").conditionalFormats.add("containsText", { text: "Accepted", format: { fill: green, font: { color: "#375623", bold: true } } });
mr.getRange("A:A").format.columnWidth=6; mr.getRange("B:B").format.columnWidth=26; mr.getRange("C:C").format.columnWidth=34; mr.getRange("D:E").format.columnWidth=22; mr.getRange("F:G").format.columnWidth=16; mr.getRange("H:L").format.columnWidth=14;
mr.freezePanes.freezeRows(4); mr.tables.add("A4:L32", true, "MigrationRegisterTable").style = "TableStyleMedium2";

const recon = baseSheet("Reconciliation", "Migration Reconciliation", "Enter source and Odoo totals after each dry run. Tolerance must be explicitly approved; default is zero.", "J");
recon.getRange("A4:J4").values = [["Control","Source register","Odoo source of truth","Source total","Odoo total","Tolerance","Result","Owner","Evidence","Sign-off date"]];
const reconRows = [
  ["Inventory = GL","Inventory valuation extract","Stock Valuation vs Inventory GL"],
  ["AR = Aging","Customer aging","Receivable ledger / aging"],
  ["AP = Aging","Supplier aging","Payable ledger / aging"],
  ["Retention Receivable","Contract retention register","IPC deductions / receivable"],
  ["Retention Payable","Subcontract retention register","Certificate deductions / payable"],
  ["Advances","Advance registers","Advance accounts and contracts"],
  ["Project Actuals","Legacy project cost","Analytic ledger"],
  ["Open Commitments","Open PO / subcontract","Remaining commitments"],
  ["Certified","IPC register","Certified IPCs"],
  ["Billed / Collected","Invoice and receipt registers","Invoices and reconciled payments"],
];
recon.getRange("A5:J14").values = reconRows.map(r=>[...r,0,0,0,null,"","",null]);
recon.getRange("G5:G14").formulas = reconRows.map((_,i)=>[`=IF(ABS(E${i+5}-D${i+5})<=F${i+5},\"PASS\",\"FAIL\")`]);
header(recon.getRange("A4:J4")); body(recon.getRange("A5:J14"));
recon.getRange("D5:F14").format.numberFormat = "#,##0.00"; recon.getRange("J5:J14").format.numberFormat = "yyyy-mm-dd";
recon.getRange("G5:G14").conditionalFormats.add("containsText", { text: "PASS", format: { fill: green, font: { color: "#375623", bold: true } } });
recon.getRange("G5:G14").conditionalFormats.add("containsText", { text: "FAIL", format: { fill: red, font: { color: "#9C0006", bold: true } } });
recon.getRange("A:C").format.columnWidth=26; recon.getRange("D:G").format.columnWidth=15; recon.getRange("H:I").format.columnWidth=22; recon.getRange("J:J").format.columnWidth=14; recon.freezePanes.freezeRows(4);

const uat = baseSheet("UAT Scenarios", "Golden UAT Scenarios", "Execute on named pilot users with evidence. Financial posting steps remain manual and require Finance authorization.", "J");
uat.getRange("A4:J4").values = [["ID","Scenario","Scope","Business owner","Tester","Evidence link / reference","Defect ID","Status","Sign-off date","Notes"]];
const uatRows = [
  ["GS-01","Tender to Award","Lead → Tender → BOQ → Estimate → Bid Approval → Award → Project Bootstrap"],
  ["GS-02","Procure to Consume","MR / stock check → RFQ → PO → Receipt → MIR → Issue → Consumption → Bill / payment control"],
  ["GS-03","Subcontract to Pay","Subcontract BOQ → Advance → Measurement → Certificate → Retention / recovery → Draft Bill → Release"],
  ["GS-04","Measure to Cash","WIR → Measurement → IPC → Deductions → Draft Invoice → ETA readiness → Collection tracking"],
  ["GS-05","Variation / Claim / EOT","RFI → Potential Change → Notice → Estimate → Approval → Contract / budget update"],
  ["GS-06","Monthly Close and Closeout","Commitment / Actual / Accrual → ETC/EAC/WIP → Dashboard → Handover → DLP → Final Account"],
];
uat.getRange("A5:J10").values = uatRows.map(r=>[...r,"","","","","Not Started",null,""]);
header(uat.getRange("A4:J4")); body(uat.getRange("A5:J10"));
uat.getRange("H5:H10").dataValidation = { rule: { type: "list", values: ["Not Started","In Progress","Blocked","Failed","Passed"] } };
uat.getRange("H5:H10").conditionalFormats.add("containsText", { text: "Passed", format: { fill: green, font: { color: "#375623", bold: true } } });
uat.getRange("H5:H10").conditionalFormats.add("containsText", { text: "Failed", format: { fill: red, font: { color: "#9C0006", bold: true } } });
uat.getRange("I5:I10").format.numberFormat="yyyy-mm-dd";
uat.getRange("A:A").format.columnWidth=10; uat.getRange("B:B").format.columnWidth=24; uat.getRange("C:C").format.columnWidth=56; uat.getRange("D:E").format.columnWidth=20; uat.getRange("F:G").format.columnWidth=24; uat.getRange("H:J").format.columnWidth=16; uat.freezePanes.freezeRows(4);

const cut = baseSheet("Cutover Checklist", "Controlled Cutover Checklist", "Go/No-Go is blocked until every mandatory gate is Complete and evidence is attached.", "H");
cut.getRange("A4:H4").values = [["Seq","Gate / activity","Environment","Owner","Mandatory","Status","Evidence / reference","Rollback trigger"]];
const cutRows = [
  [1,"Staging clone refreshed","Staging","Technical Lead","Yes"],[2,"Approved configuration baseline applied","Staging","Functional Lead","Yes"],[3,"All custom modules tested","Development / Staging","Technical Lead","Yes"],
  [4,"Functional UAT signed","Staging","Process Owners","Yes"],[5,"Pilot project completed","Staging","Project Sponsor","Yes"],[6,"Parallel run reconciled","Staging","Finance / Operations","Yes"],
  [7,"Security and SoD approved","Staging","Security Owner","Yes"],[8,"Arabic / RTL and reports accepted","Staging","Business Owners","Yes"],[9,"Migration dry run accepted","Staging","Migration Lead","Yes"],
  [10,"Production backup verified","Production","Odoo.sh Owner","Yes"],[11,"Go / No-Go approval recorded","Governance","Executive Sponsor","Yes"],[12,"Controlled module deployment","Production","Technical Lead","Yes"],
  [13,"Opening data migration","Production","Migration / Finance","Yes"],[14,"Smoke test and reconciliation","Production","UAT Leads","Yes"],[15,"Hypercare opened","Production","Support Lead","Yes"],[16,"Post-go-live review","Production","Steering Committee","Yes"],
];
cut.getRange("A5:H20").values = cutRows.map(r=>[...r,"Not Started","",""]);
header(cut.getRange("A4:H4")); body(cut.getRange("A5:H20"));
cut.getRange("F5:F20").dataValidation = { rule: { type: "list", values: ["Not Started","In Progress","Complete","Blocked","Rollback"] } };
cut.getRange("F5:F20").conditionalFormats.add("containsText", { text: "Complete", format: { fill: green, font: { color: "#375623", bold: true } } });
cut.getRange("F5:F20").conditionalFormats.add("containsText", { text: "Blocked", format: { fill: red, font: { color: "#9C0006", bold: true } } });
cut.getRange("A:A").format.columnWidth=6; cut.getRange("B:B").format.columnWidth=38; cut.getRange("C:C").format.columnWidth=22; cut.getRange("D:D").format.columnWidth=22; cut.getRange("E:F").format.columnWidth=14; cut.getRange("G:H").format.columnWidth=34; cut.freezePanes.freezeRows(4);

const master = baseSheet("Master Data", "Master Data Import Staging", "Use stable external IDs and company/project codes. This sheet is a staging template, not a direct import authorization.", "M");
master.getRange("A4:M4").values = [["Object type","External ID","Company code","Record code","Name","Parent external ID","Currency","Language","Effective from","Effective to","Active","Source reference","Validation status"]];
master.getRange("A5:M29").values = Array.from({length:25},()=>["","","","","","","","",null,null,true,"","Not Checked"]);
header(master.getRange("A4:M4")); body(master.getRange("A5:M29"));
master.getRange("A5:A29").dataValidation = { rule: { type: "list", values: ["Company","Branch","Partner","Product Category","Product","UoM","Cost Code","WBS","Location","Warehouse","Equipment","Vehicle","User"] } };
master.getRange("M5:M29").dataValidation = { rule: { type: "list", values: ["Not Checked","Valid","Rejected"] } };
master.getRange("I5:J29").format.numberFormat="yyyy-mm-dd"; master.getRange("A:F").format.columnWidth=21; master.getRange("G:M").format.columnWidth=16; master.freezePanes.freezeRows(4);

const projects = baseSheet("Projects Contracts", "Project and Contract Import Staging", "Projects must link to an approved company, analytic account and contract context before dependent BOQ or transaction loads.", "N");
projects.getRange("A4:N4").values = [["External ID","Project code","Project name","Company code","Analytic account code","Contract external ID","Contract type","Partner external ID","Currency","Original value","Start date","End date","State","Validation status"]];
projects.getRange("A5:N29").values = Array.from({length:25},()=>["","","","","","","","","",0,null,null,"Draft","Not Checked"]);
header(projects.getRange("A4:N4")); body(projects.getRange("A5:N29")); projects.getRange("J5:J29").format.numberFormat="#,##0.00"; projects.getRange("K5:L29").format.numberFormat="yyyy-mm-dd";
projects.getRange("M5:M29").dataValidation={rule:{type:"list",values:["Draft","Review","Approved","Active"]}}; projects.getRange("N5:N29").dataValidation={rule:{type:"list",values:["Not Checked","Valid","Rejected"]}};
projects.getRange("A:I").format.columnWidth=20; projects.getRange("J:N").format.columnWidth=16; projects.freezePanes.freezeRows(4);

const boq = baseSheet("BOQ Budget Lines", "BOQ and Budget Line Staging", "One row per source line. Preserve external IDs, revision, WBS, cost code, location and currency context.", "P");
boq.getRange("A4:P4").values = [["BOQ external ID","Revision","Line external ID","Parent section ID","Project code","Contract external ID","BOQ type","Item code","Description","UoM","Quantity","Unit rate / cost","Amount check","WBS code","Cost code","Validation status"]];
boq.getRange("A5:P29").values = Array.from({length:25},()=>["",0,"","","","","Sell","","","",0,0,null,"","","Not Checked"]);
boq.getRange("M5:M29").formulas = Array.from({length:25},(_,i)=>[`=K${i+5}*L${i+5}`]);
header(boq.getRange("A4:P4")); body(boq.getRange("A5:P29")); boq.getRange("G5:G29").dataValidation={rule:{type:"list",values:["Sell","Cost"]}}; boq.getRange("P5:P29").dataValidation={rule:{type:"list",values:["Not Checked","Valid","Rejected"]}};
boq.getRange("K5:M29").format.numberFormat="#,##0.00"; boq.getRange("A:H").format.columnWidth=19; boq.getRange("I:I").format.columnWidth=38; boq.getRange("J:P").format.columnWidth=16; boq.freezePanes.freezeRows(4);

const open = baseSheet("Open Transactions", "Open Transaction Staging", "Load only open, reconciled source positions after the related master data. Draft standard documents remain under Finance/Operations control.", "N");
open.getRange("A4:N4").values = [["Document type","External ID","Company code","Project code","Contract external ID","Partner external ID","Document date","Due date","Currency","Gross amount","Open amount","Source state","Source reference","Validation status"]];
open.getRange("A5:N29").values = Array.from({length:25},()=>["","","","","","",null,null,"",0,0,"","","Not Checked"]);
header(open.getRange("A4:N4")); body(open.getRange("A5:N29")); open.getRange("A5:A29").dataValidation={rule:{type:"list",values:["Purchase Order","Subcontract","IPC","Vendor Bill","Customer Advance","Supplier Advance","Retention Receivable","Retention Payable","Guarantee"]}}; open.getRange("N5:N29").dataValidation={rule:{type:"list",values:["Not Checked","Valid","Rejected"]}};
open.getRange("G5:H29").format.numberFormat="yyyy-mm-dd"; open.getRange("J5:K29").format.numberFormat="#,##0.00"; open.getRange("A:F").format.columnWidth=21; open.getRange("G:N").format.columnWidth=16; open.freezePanes.freezeRows(4);

const balances = baseSheet("Opening Balances", "Opening Balance Staging — Approval Required", "HIGH RISK: do not import or post until Finance approves accounts, journals, dates, currencies, analytic dimensions and reconciliation.", "P");
balances.getRange("A4:P4").values = [["Batch","Line external ID","Company code","Journal code","Accounting date","Account code","Partner external ID","Currency","Amount currency","Debit","Credit","Project code","Analytic account","Cost code","Source reference","Approval status"]];
balances.getRange("A5:P29").values = Array.from({length:25},()=>["","","","",null,"","","",0,0,0,"","","","","Blocked"]);
header(balances.getRange("A4:P4")); body(balances.getRange("A5:P29")); balances.getRange("E5:E29").format.numberFormat="yyyy-mm-dd"; balances.getRange("I5:K29").format.numberFormat="#,##0.00";
balances.getRange("P5:P29").dataValidation={rule:{type:"list",values:["Blocked","Finance Reviewed","Approved for Dry Run","Rejected"]}}; balances.getRange("P5:P29").conditionalFormats.add("containsText",{text:"Blocked",format:{fill:red,font:{color:"#9C0006",bold:true}}});
balances.getRange("A:H").format.columnWidth=18; balances.getRange("I:P").format.columnWidth=17; balances.freezePanes.freezeRows(4);

const issues = baseSheet("Issue Log", "UAT and Hypercare Issue Log", "Use one issue per row with reproducible evidence and an owner. Critical issues block cutover until closed or formally waived.", "J");
issues.getRange("A4:J4").values = [["Issue ID","Phase","Severity","Process / module","Description","Owner","Due date","Status","Resolution / evidence","Closed date"]];
issues.getRange("A5:J34").values = Array.from({length:30},(_,i)=>[`ISS-${String(i+1).padStart(3,"0")}`,"UAT","Medium","","","",null,"Open","",null]);
header(issues.getRange("A4:J4")); body(issues.getRange("A5:J34")); issues.getRange("B5:B34").dataValidation={rule:{type:"list",values:["Migration","UAT","Pilot","Parallel Run","Cutover","Hypercare"]}}; issues.getRange("C5:C34").dataValidation={rule:{type:"list",values:["Critical","High","Medium","Low"]}}; issues.getRange("H5:H34").dataValidation={rule:{type:"list",values:["Open","In Progress","Blocked","Closed","Waived"]}};
issues.getRange("G5:G34").format.numberFormat="yyyy-mm-dd"; issues.getRange("J5:J34").format.numberFormat="yyyy-mm-dd"; issues.getRange("C5:C34").conditionalFormats.add("containsText",{text:"Critical",format:{fill:red,font:{color:"#9C0006",bold:true}}}); issues.getRange("H5:H34").conditionalFormats.add("containsText",{text:"Closed",format:{fill:green,font:{color:"#375623",bold:true}}});
issues.getRange("A:D").format.columnWidth=18; issues.getRange("E:E").format.columnWidth=42; issues.getRange("F:J").format.columnWidth=18; issues.freezePanes.freezeRows(4);

for (const s of wb.worksheets.items) {
  const used = s.getUsedRange();
  used.format.font = { name: "Aptos", size: 10, color: "#1F2937" };
  s.getRange("A1").format.font = { name: "Aptos Display", size: 16, bold: true, color: "#FFFFFF" };
}

const checks = await wb.inspect({ kind: "table", range: "Summary!A1:H17", include: "values,formulas", tableMaxRows: 20, tableMaxCols: 10 });
console.log(`SUMMARY_INSPECTION ${checks.ndjson.slice(0, 1200)}`);
const errors = await wb.inspect({ kind: "match", searchTerm: "#REF!|#DIV/0!|#VALUE!|#NAME\\?|#N/A", options: { useRegex: true, maxResults: 300 }, summary: "final formula error scan" });
console.log(`FORMULA_ERROR_SCAN ${errors.ndjson.slice(0, 1200)}`);

for (const s of wb.worksheets.items) {
  const used = s.getUsedRange();
  const preview = await wb.render({ sheetName: s.name, range: used.address, scale: 0.8, format: "png" });
  await fs.writeFile(`${previewDir}/${s.name.replaceAll(" ", "_")}.png`, new Uint8Array(await preview.arrayBuffer()));
}

const out = await SpreadsheetFile.exportXlsx(wb);
await out.save(`${outputDir}/CW-150_Migration_UAT_Cutover_Control.xlsx`);
console.log(`EXPORTED ${outputDir}/CW-150_Migration_UAT_Cutover_Control.xlsx`);
