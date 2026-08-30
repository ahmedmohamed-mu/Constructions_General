# سجل قبول DEV-140 — Dashboards and User Workspaces

## النتيجة والهدف

تم تنفيذ واختبار مرحلة DEV-140 على فرع `main` المصنف Development في Odoo.sh. الهدف هو تقديم مساحات عمل حسب الدور فوق نفس مستندات النظام، مع أرقام قابلة للتتبع وعدم إنشاء جدول KPI موازي أو إدخال بيانات مكرر. البناء النهائي رقم `37195953` نجح على commit `502967c331bd273c6cbd2ca367e5a9dda2fd5e89` بتاريخ 2026-08-30.

## النطاق المنفذ

- موديول `mu_construction_dashboards` ومساحات: Executive، Project Manager، Commercial، Procurement، Finance، Quality، وMy Work.
- Executive Portfolio على `project.project` يعرض Revised Contract Value وRevised Budget وActual وEAC وForecast Variance وBilled وCollected في عملة الشركة.
- عند تعدد العقود أو العملات، تُحول كل قيمة إلى عملة الشركة بتاريخ آخر Monthly Close للعقد؛ لا يتم جمع عملات مختلفة مباشرة.
- Project Manager Workspace يعرض تقارير الموقع والمشتريات والمستخلصات والتغييرات وNCR/Snag وCloseout المفتوحة.
- Commercial يعتمد `mu.construction.contract`، Procurement يعتمد `purchase.order`، Finance يعتمد `mu.construction.monthly.close`، Quality يعتمد `quality.alert`، وMy Work يعتمد `mail.activity`.
- أزرار Drill-down من صفحة المشروع تفتح Monthly Controls وVariations وPurchase Orders وQuality Alerts وClient IPC بالسياق الصحيح للمشروع.
- الاستعلامات التشغيلية مجمعة باستخدام `_read_group`، والعقود وآخر إقفال لكل عقد تُجلب دفعيًا لتجنب N+1 عند عرض Portfolio متعدد المشاريع.
- ترجمة عربية أولية لمسميات Workspaces والمؤشرات وحالات الصحة، مع قابلية RTL القياسية في Odoo.

## النماذج والحقول والتكوين

- لا توجد نماذج KPI جديدة ولا سجلات Dashboard مخزنة.
- تم توسيع `project.project` بحقول محسوبة غير مخزنة للعملة والقيم المالية والحالة المالية والعدادات التشغيلية والحالة التشغيلية.
- القيم المالية التنفيذية محمية Field-level بمجموعة `mu_construction_core.group_construction_manager` وتُحسب بصلاحية نظام فقط بعد تحقق حق قراءة الحقل.
- قوائم Procurement وFinance وQuality تظهر فقط داخل تسلسل القوائم المناسب لمجموعات Purchase/Accounting/Quality، مع استمرار Record Rules القياسية وقواعد الشركات.
- لا توجد تغييرات Studio؛ كل الحقول والواجهات ومساحات العمل والترجمات في Git.

## الكود والاختبارات والأدلة

- Commit الإنشاء: `dfbf82d9449c5047d3003a019e905fdb57c4fd1b`.
- Commit توافق اختبار مجموعات Odoo 19: `3be2ccb26d7957e07608d4fe2a717af9393af3df`.
- Commit معالجة تعريف View في Odoo 19: `666ef5873c7273ab9f42912074baeda4e3e69787`.
- Commit النهائي: `502967c331bd273c6cbd2ca367e5a9dda2fd5e89`.
- Odoo سجل للموديول `6 tests`, زمن `0.64s` و`392 queries`.
- تحميل الموديول: `0.96s` متضمنًا `0.64s` اختبار، و`273 queries (+392 test, +273 other)`.
- نتيجة Regression الكلية: `0 failed, 0 error(s) of 64 tests`.
- الاختبارات تثبت مصالحة Contract/Budget/Actual/EAC/Variance، عدادات التشغيل، عدم إنشاء أي سجل تشغيلي عند القراءة، Drill-down للمصدر، منع المستخدم العادي من قراءة المؤشرات المالية التنفيذية، ونطاق My Work.
- `outputs/DEV-140_evidence/01-build-success.jpg` — Build `37195953` بحالة Success.
- `outputs/DEV-140_evidence/02-module-test-log.jpg` — تشغيل اختبارات الموديول وسطر التحميل.
- `outputs/DEV-140_evidence/03-regression-result.jpg` — نجاح 64 اختبارًا لجميع الموديولات.

## الأثر الأمني والمحاسبي والبياني

- الحماية المالية ليست إخفاء Menu فقط؛ اختبار Odoo أثبت `Access Denied` عند محاولة Construction User قراءة `dashboard_contract_value`.
- `compute_sudo` لا يمنح حق قراءة الحقل؛ يستخدم فقط لحساب KPI للمدير المصرح له بدون تعطل بسبب نقص مجموعات التطبيقات التابعة.
- لا ينشئ الموديول Invoice أو Bill أو Journal Entry أو Payment أو Stock Move، ولا يغير أي مستند مصدر.
- قراءة Workspaces لا تنشئ Contract أو Monthly Close أو Change أو Quality Alert أو Purchase Order؛ الاختبار يقارن أعداد السجلات قبل القراءة وبعدها.
- لم يتم تحميل بيانات حقيقية أو أرصدة مالية ولم يتم النشر إلى Production.

## المخاطر والملاحظات وRollback

- Portfolio المالي يعتمد آخر Monthly Close غير ملغى لكل عقد؛ لذلك جودة KPI مرتبطة بانضباط الإقفال الشهري وإقفاله بعد المراجعة.
- القيم التنفيذية تُعرض بعملة الشركة، بينما يبقى المستند الأصلي بعملة العقد ويمكن تتبعه عبر Drill-down.
- اتصال Odoo.sh البصري نجح ووصل إلى قاعدة Development، لكن المستخدم المؤقت الذي منحه Odoo.sh للاتصال لا يحمل Construction Groups؛ لقطة القوائم حسب الدور تُستكمل ضمن Role-based UAT بمستخدمين مسمين في CW-150.
- Rollback: revert لcommits الموديول ثم Upgrade في Development build جديد. لا توجد حقائق Dashboard مخزنة تحتاج حذفًا أو ترحيلًا.

## قرار البوابة والخطوة التالية

DEV-140 مقبول تقنيًا ووظيفيًا على Development وفق التفويض الشامل المسجل في المهمة، مع نجاح البناء والأمان والمصالحة وعدم تكرار البيانات. يسمح هذا السجل بالانتقال إلى CW-150 — Migration, UAT, Pilot and Cutover. لا يعد ذلك تصريحًا بتحميل أرصدة مالية حقيقية أو الترحيل إلى Production؛ هذه الإجراءات تبقى مرتبطة بملفات البيانات الفعلية ومصالحتها وقرار Cutover منفصل.
