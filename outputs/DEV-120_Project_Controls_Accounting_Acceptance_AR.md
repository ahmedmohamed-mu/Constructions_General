# سجل قبول DEV-120 — Project Controls and Accounting

## النتيجة

تم تنفيذ واختبار مرحلة DEV-120 على فرع `main` المصنف Development في Odoo.sh. البناء النهائي رقم `37194733` نجح على commit `4ef912341e1df5d9f4ad4fd3b2bee6449a85d42f` بتاريخ 2026-08-30.

## النطاق المنفذ

- موديول `mu_construction_project_controls` معتمد على النماذج القياسية والموديولات الإنشائية القائمة، بدون تكرار أوامر الشراء أو الفواتير أو القيود.
- Project Controls Profile فعال بالتاريخ وعلى مستوى الشركة أو المشروع، ويحدد طريقة الاعتراف بالإيراد ومسؤولي المراجعة والاعتماد.
- Monthly Close موحد لكل مشروع/عقد/تاريخ إقفال، بمسار: Draft → Data Collection → PM Review → Commercial Review → Finance Review → Approved → Locked.
- Snapshot حسب Cost Code يشمل Original Budget، Revised Budget، Commitments، Actual، Accruals، Cost to Date، ETC، EAC، وForecast Variance.
- الالتزامات تُحتسب من أوامر الشراء المؤكدة فقط وحتى تاريخ الإقفال، مع استبعاد المسودات والمبالغ المفوترة.
- Actuals تُقرأ من بنود القيود المرحلة فقط وبسياق المشروع/الحساب التحليلي، ولا يتم إنشاء أو ترحيل أي قيد.
- Accrual Worksheet مرتبط بأمر الشراء أو مستخلص المقاول، مع تاريخ عكس وأساس احتساب ومسار اعتماد؛ الموديول لا يرحّل قيودًا.
- Earned Value: PV، EV، AC، CV، SV، CPI، SPI.
- WIP يفصل بين Earned/Recognized، Certified، Billed، وCollected، ويحسب Contract Asset أو Contract Liability وExpected Margin.
- طرق الاعتراف المدعومة: Cost-to-Cost، Output/Physical Progress، وMilestone/Manual Earned Value.
- Cash Flow Forecast باحتمالية وقيمة مرجحة، وربط اختياري بمستخلص العميل أو أمر الشراء.
- القفل داخلي على Snapshot المشروع ولا يغيّر Accounting Lock Dates.
- صلاحيات متعددة الشركات، Chatter، Activities، Next Responsible، وقفل السجلات المعتمدة.

## ضوابط السلامة المثبتة

- لا توجد أي دالة لترحيل Journal Entry أو Invoice أو Payment.
- لا يتم إنشاء قيود اعتراف إيراد أو Accrual تلقائيًا.
- لا يتم تعديل إعدادات الضرائب أو الجورنالات أو الحسابات أو Lock Dates.
- المستند المعتمد لا يُحذف أو يُعدل؛ تتم المعالجة في فترة لاحقة أو بتسوية محكومة.

## الاختبارات

- 6 اختبارات خاصة بالموديول تغطي EAC/variance، EVM، WIP cost-to-cost، contract asset، استبعاد PO draft، إدراج PO confirmed داخل الفترة، قفل الإقفال، عدم إنشاء قيود، وضوابط accrual/cash-flow.
- نتيجة البناء الكلية: `0 failed, 0 error(s) of 52 tests`.
- زمن تحميل الموديول: `1.22s` متضمنًا `0.75s` اختبارات، بعدد `483 queries (+523 test)`.

## أدلة القبول

- `outputs/DEV-120_evidence/01-build-success.jpg` — Odoo.sh Build `37194733` بحالة Success.
- `outputs/DEV-120_evidence/02-test-log.jpg` — سطر تحميل الموديول ونتائج الاختبارات.
- الكود النهائي: commit `4ef912341e1df5d9f4ad4fd3b2bee6449a85d42f`.

## قرار البوابة

DEV-120 مقبول تقنيًا ووظيفيًا ضمن قاعدة Development. لا توجد معاملة مالية حقيقية أو نشر Production ضمن هذه المرحلة. يسمح هذا السجل بالانتقال إلى DEV-130 — Equipment and Closeout.
