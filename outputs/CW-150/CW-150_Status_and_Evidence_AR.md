# سجل حالة CW-150 — Migration, UAT and Cutover

## النتيجة الحالية

تم تجهيز أدوات التحكم والتوثيق اللازمة لبدء التنفيذ الفعلي للمرحلة، دون تحميل بيانات حقيقية أو تغيير Production. الحالة **Prepared / Execution Blocked** وليست Accepted.

## الأعمال المكتملة بأدلة

- حزمة التحكم على commit `1005a688caaed806f1083143bad8185508a3cb8c`، ونجح لها Odoo.sh Development build رقم `37196335` على Odoo 19 خلال `0:03:36`.
- Workbook موحد للـMigration Register وReconciliation وGolden UAT وCutover وIssue Log.
- 28 كائن ترحيل مرتبة حسب الاعتماد، مع Source/Imported/Rejected counts وCount variance وصيغة قبول.
- 10 مصالحات بقواعد Tolerance وPASS/FAIL وصفر افتراضي.
- 6 سيناريوهات Golden end-to-end مرتبطة بكل مراحل النظام.
- 16 بوابة Cutover، وكلها Mandatory وNot Started، وProduction approval محظور افتراضيًا.
- قوالب Staging للـMaster Data والمشروعات والعقود وBOQ/Budget والمستندات المفتوحة والأرصدة الافتتاحية.
- Opening Balances موسومة High Risk وحالة Approval الافتراضية Blocked.
- Formula scan النهائي: صفر تطابق مع `#REF!`, `#DIV/0!`, `#VALUE!`, `#NAME?`, `#N/A`.
- مراجعة بصرية لكل أوراق الـWorkbook بعد التصدير.
- Runbook للـDry Runs والمصالحة وPilot/Parallel وGo/No-Go وHypercare وRollback.
- `outputs/CW-150_evidence/01-build-success.jpg` — دليل نجاح build `37196335` وربطه بالـcommit أعلاه.
- Validator مستقل Read-only لملفات CSV يغطي Schema الكائنات الـ28، ويفحص الأعمدة والقيم المطلوبة والتكرار والمراجع والتواريخ والأرقام واتزان Opening Balances قبل أي Import.
- نتيجة الاختبارات المحلية للـValidator: `6 tests`, كلها Passed، وتشمل valid path وnegative data rules والتقارير وعدد كائنات الـSchema.

## ما لم ينفذ عمدًا

- لا استيراد بيانات عميل أو أرصدة مالية.
- لا Posting لفاتورة أو قيد أو دفعة.
- لا إعداد ETA بأسرار حقيقية.
- لا ترقية أو نشر Production.
- لا توقيع UAT أو Cutover نيابة عن ملاك الأعمال.

## الأدلة المطلوبة لإغلاق المرحلة

1. ملفات المصدر الفعلية وخرائطها وتوقيعات ملاك البيانات.
2. سجل DR-1 وDR-2 على Staging مع counts وrejects ومدة التنفيذ.
3. Reconciliation كاملة وموقعة من Finance/Operations.
4. أدلة Golden UAT لكل مستخدم مسمى ودور.
5. Security/SoD UAT وPerformance evidence على الحجم المستهدف.
6. Pilot/Parallel acceptance.
7. Backup restore test وRPO/RTO مثبتان.
8. محضر Go/No-Go يحدد build/commit والنافذة والـrollback owner.
9. تصريح منفصل صريح لأي Opening Balances أو Production cutover.

## قرار البوابة

لا يمكن اعتبار CW-150 مكتملة قبل استلام المدخلات وتنفيذ البنود السابقة. الحزمة الحالية تضمن أن بدء الترحيل سيكون قابلًا للتتبع وقابلًا للإيقاف والاستعادة، وتمنع اعتبار إعداد القوالب تفويضًا للمعاملات المالية أو Production.
