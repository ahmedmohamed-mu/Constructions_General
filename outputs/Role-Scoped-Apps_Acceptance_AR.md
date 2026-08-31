# قبول تقسيم تطبيقات المقاولات حسب الدور

## النتيجة

تم إلغاء واجهة التطبيق الجامع، وتحويل كل مجال تشغيلي إلى تطبيق مستقل ومترابط مع نماذج Odoo القياسية. ظهور التطبيق وصلاحيات النموذج يعتمدان الآن على دور المستخدم، وليس على مجموعة Construction عامة تمنح كل الوظائف.

## التطبيقات المستقلة

- Construction Dashboards
- Tender & Estimation
- Contracts & BOQ
- Project Setup
- Procurement & Inventory
- Subcontract Management
- Site Execution
- Document Control
- QA / QC
- Client Measurement & IPC
- Variations, Claims & EOT
- Project Controls
- Equipment & Closeout
- Construction Setup، لمدير النظام فقط

## نموذج الصلاحيات

لكل مجال امتياز مستقل بقيم `None / User / Manager`. المجموعة المشتركة تمنح سياق المشروع القياسي فقط، بينما تمنح مجموعات المجال صلاحيات النماذج الخاصة به. مدير النظام يرث مديري المجالات لأغراض الإدارة والدعم.

تم فصل Document Control عن QA/QC، وفصل Tender عن Contracts & BOQ. يؤكد الاختبار أن Tender User يستطيع إنشاء Tender ولا يحصل على صلاحية إنشاء Contract.

## التكامل مع Odoo القياسي

- كل الأدوار الإنشائية تستخدم تطبيق Project القياسي وسجل `project.project` نفسه.
- Procurement & Inventory يستخدم `purchase.order` و`stock.picking` القياسيين، وتمنح مجموعته صلاحيات Purchase وInventory المناسبة.
- العقود وBOQ والموقع والجودة وIPC والتغييرات والإقفال تشترك في المشروع والعقد وWBS وCost Code والموقع والحساب التحليلي من دون نسخ البيانات.
- لم يتم إنشاء بدائل للفواتير أو أوامر الشراء أو التحويلات أو المشروعات أو المهام.

## الاختبارات والأدلة

- commit: `3be593e060266de7d5ab53080182948f35636858`
- Odoo.sh Development build: `37249878`
- النتيجة: Success، مدة البناء `0:03:19`.
- تم التحقق بصريًا من ظهور التطبيقات المستقلة في Home.
- تم التحقق بصريًا من ظهور User/Manager منفصل لكل مجال في صلاحيات المستخدم.
- `Role-Scoped-Apps_evidence/01-independent-apps-home.jpg`
- `Role-Scoped-Apps_evidence/02-role-permissions-section.jpg`

## الأثر والرجوع

هذا التغيير لا ينشر معاملات مالية ولا يغير قيودًا أو فواتير. المستخدمون غير الإداريين الذين كانت لديهم المجموعة العامة القديمة يحتاجون تعيين الأدوار التشغيلية المناسبة لهم. يمكن الرجوع بعكس commit المذكور ثم إعادة بناء Development.
