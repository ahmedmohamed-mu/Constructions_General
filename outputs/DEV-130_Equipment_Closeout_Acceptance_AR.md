# سجل قبول DEV-130 — Equipment and Closeout

## النتيجة والهدف

تم تنفيذ واختبار مرحلة DEV-130 على فرع `main` المصنف Development في Odoo.sh. الهدف هو ربط تشغيل المعدات والاختبارات والتسليم وفترة ضمان العيوب والحساب الختامي وطلبات الإفراج بسياق المشروع والعقد القياسي، مع منع أي ترحيل مالي تلقائي. البناء النهائي رقم `37195362` نجح على commit `59953d1b79e260890befa06e0bdf5f8a91f239c4` بتاريخ 2026-08-30.

## الأعمال والتكوين المنفذ

- إنشاء موديول `mu_construction_equipment_closeout` مع إعادة استخدام `maintenance.equipment` و`fleet.vehicle` و`maintenance.request` و`documents.document` و`quality.alert` والعقد الإنشائي القائم.
- Equipment Rate Profile فعال بالتاريخ وعلى مستوى الشركة أو المشروع، ويمنع احتساب الأصل كمعدة مملوكة ومؤجرة في الوقت نفسه.
- تثبيت Snapshot لمعدل التشغيل الداخلي أو الإيجار وتكلفة الوقود وCost Code على سطر الاستخدام عند اعتماد التقرير اليومي.
- إظهار التكلفة التشغيلية المعتمدة في Monthly Close كقيمة تحليلية مستقلة، مع تحويلها من عملة الشركة إلى عملة العقد بتاريخ الاستخدام، واستبعادها من Ledger Actual وEAC لمنع الازدواج.
- ربط الاستخدام بطلب صيانة قياسي مع Project/Contract/Location/WBS/Cost Code context.
- مسارات Testing & Commissioning، Handover، DLP/Defects، Final Account، وRetention/Guarantee Release، مع Creator/Reviewer/Approver/Next Responsible وActivities وChatter.
- منع التسليم مع Snag/NCR مفتوح أو Checklist/Commissioning غير مكتمل، ومنع إغلاق DLP قبل إغلاق العيوب وإرفاق دليل شهادة الإغلاق.
- تسوية الحساب الختامي في عملة العقد مع فصل Certified وBilled وCollected وRetention Held وOutstanding Balance.
- تحديث حالة الإغلاق وتاريخ Practical Completion ونهاية DLP على العقد بدون إنشاء نسخة بديلة من العقد أو المشروع.

## النماذج والحقول الرئيسية

- نماذج جديدة: `mu.construction.equipment.rate`، `mu.construction.closeout.profile`، `mu.construction.commissioning`، `mu.construction.handover`، `mu.construction.handover.checklist`، `mu.construction.dlp`، `mu.construction.dlp.defect`، `mu.construction.final.account`، و`mu.construction.release.request`.
- نماذج ممتدة: `mu.construction.daily.equipment`، `mu.construction.daily.site.report`، `maintenance.request`، `mu.construction.contract`، `mu.construction.monthly.close`، و`mu.construction.monthly.close.line`.
- حقول التقارير المهمة معرفة في الكود، ومنها `analytic_equipment_cost` و`equipment_analytic_cost` و`total_equipment_analytic_cost` وحقول حالة الإغلاق على العقد؛ لا تعتمد هذه المرحلة على حقول Studio من نوع `x_studio`.

## الواجهات وStudio

- قوائم ونماذج مستقلة داخل Construction Operations للمعدات والإغلاق، مع قوائم إعدادات لمعدلات المعدات وCloseout Profiles.
- توسيع تقرير الموقع اليومي وطلب الصيانة وMonthly Close لإظهار السياق والنتائج التحليلية.
- لا توجد تغييرات Studio في هذه المرحلة؛ جميع عناصر المنطق والتقارير والأمان معرفة في الموديول ومخزنة في Git.

## الكود والاختبارات والأدلة

- Commit الإنشاء: `178d6122eaa96583292003e1d4122444b06a56e7`.
- Commit المراجعة النهائية: `59953d1b79e260890befa06e0bdf5f8a91f239c4`.
- نتيجة البناء الكلية: `0 failed, 0 error(s) of 60 tests`.
- إحصاء Odoo للموديول: `9 tests`, زمن الاختبار `0.72s` و`520 queries`.
- تحميل الموديول: `1.69s` متضمنًا `0.73s` اختبارات، و`1208 queries (+520 test, +1208 other)`.
- `outputs/DEV-130_evidence/01-build-success.jpg` — Build `37195362` بحالة Success.
- `outputs/DEV-130_evidence/02-module-test-log.jpg` — تشغيل اختبارات الموديول وسطر التحميل.
- `outputs/DEV-130_evidence/03-regression-result.jpg` — نتيجة 60 اختبارًا وإحصاءات كل الموديولات.

## الأمان والأثر المحاسبي والبيانات

- Record Rules متعددة الشركات لكل معدلات المعدات وسجلات الإغلاق، وصلاحيات Create/Read/Write/Unlink موزعة على Construction User/Manager، مع تحقق من المستخدم المسؤول عند الانتقالات الحرجة.
- السجلات المعتمدة مقفلة، ولا تحذف مستندات Closeout بعد انتقالها خارج Draft وفق قواعد كل Workflow.
- لا ينشئ الموديول Invoice أو Bill أو Journal Entry أو Payment ولا يرحّل أي مستند مالي. طلب الإفراج يسجل الموافقة والمرجع فقط، وتظل المعالجة المالية لدى Finance في المستند القياسي المناسب.
- لا توجد بيانات تشغيل أو أرصدة مالية حقيقية مستوردة؛ بيانات الاختبار معزولة داخل بناء Odoo.sh ويتم التخلص منها بعد الاختبار.

## المخاطر والملاحظات المعروفة

- أسعار التشغيل ومدة DLP ومسؤولو الاعتماد يجب تهيئتهم ببيانات الشركة الفعلية قبل UAT؛ النظام يمنع الاعتماد عند غياب Profile فعال.
- تكلفة المعدات المعروضة في Monthly Close تحليلية فقط. المصروف المحاسبي الفعلي يظل قادمًا من القيود المرحلة، وتجب المصالحة بينهما في UAT لتجنب تفسيرهما كمبلغين قابلين للجمع.
- اعتماد العميل الفعلي ومستندات التسليم والإفراج تحتاج Golden Scenario وUser Sign-off في CW-150.
- ترجمة المصطلحات العربية وتحسين RTL النهائيان ضمن حزمة UAT/localization، بينما البنية الحالية قابلة للترجمة ولا تغير Odoo core.

## Rollback

- الرجوع الآمن في Development يتم بعمل revert للـcommits الخاصة بالمرحلة ثم Upgrade للموديولات التابعة داخل Build جديد مع نسخة احتياطية.
- لا يحذف الـrollback سجلات معتمدة. إذا وُجدت بيانات اختبار مرتبطة، يوقف الموديول عن الاستخدام وتجرى migration محافظة أو أرشفة قبل أي uninstall.
- لم يتم تنفيذ أي نشر Production أو أي معاملة غير قابلة للعكس في هذه المرحلة.

## قرار البوابة والخطوة التالية

DEV-130 مقبول تقنيًا ووظيفيًا على قاعدة Development وفق التفويض الشامل المسجل في المهمة، وبأدلة بناء واختبارات قابلة للتتبع. يسمح هذا السجل بالانتقال إلى DEV-140 — Dashboards and User Workspaces. يبقى اعتماد المستخدمين النهائيين على السيناريوهات الواقعية جزءًا من CW-150.
