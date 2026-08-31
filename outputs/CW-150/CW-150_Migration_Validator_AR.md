# CW-150 — أداة فحص ملفات الترحيل

## الهدف

فحص ملفات CSV قبل أي Import إلى Odoo. الأداة Read-only بالنسبة إلى Odoo: لا تتصل بقاعدة البيانات ولا تستخدم ORM ولا تنشئ أو تعدل مستندات. مخرجاتها تقرير JSON للاستخدام الآلي وتقرير Markdown للمراجعة والتوقيع.

## النطاق

يغطي Schema كل الكائنات الـ28 بالترتيب المعتمد في الخطة. يفحص:

- وجود الملفات والأعمدة المطلوبة.
- القيم الإلزامية وExternal IDs.
- المفاتيح المكررة، بما فيها الأكواد داخل الشركة عند الحاجة.
- المراجع بين الشركات والمشروعات والعقود والشركاء والمنتجات والمخازن وCost Codes.
- صيغة التاريخ `YYYY-MM-DD`.
- صحة القيم الرقمية.
- اتزان Debit/Credit لكل Batch + Company + Currency في ملف الأرصدة الافتتاحية.
- منع Debit وCredit معًا في نفس السطر ومنع القيم السالبة.

الأداة لا تعتمد Tax/Journals/Accounts أو نسبًا hard-coded. فرق الاتزان الافتراضي صفر ويمكن تغييره صراحة في Dry Run موثق.

## التشغيل

إنشاء Pack فارغ من 28 CSV Template وManifest:

```powershell
python tools/cw150_generate_templates.py C:\migration\templates
```

المولد يرفض الكتابة فوق أي Template موجود افتراضيًا. يستخدم `--force` فقط عند الرغبة الصريحة في إعادة توليد Pack فارغ؛ لذلك تحفظ ملفات البيانات المعبأة في مسار منفصل وتحت Version/Backup مناسب.

يوجد Pack جاهز للتسليم في `outputs/CW-150/CW-150_Migration_CSV_Templates.zip`، ويحتوي 28 CSV Template و`cw150_template_manifest.json`. SHA-256 للإصدار الحالي: `3507C2B39C7FFCC0ED5A5F46A43C3EFDACA28125C5B8FC9009F1EC07EA3B2121`.

فحص الملفات المعبأة:

```powershell
python tools/cw150_migration_validator.py C:\migration\extracts `
  --output-dir C:\migration\reports `
  --require-all `
  --balance-tolerance 0
```

النتائج:

- Exit code `0`: لا توجد أخطاء؛ قد توجد Warnings إذا لم يستخدم `--require-all`.
- Exit code `1`: اكتملت عملية الفحص ووجدت أخطاء بيانات.
- Exit code `2`: تعذر تشغيل الأداة أو قراءة Schema/الملفات.

لا تعني نتيجة صفر أن الملفات مصرح باستيرادها. يلزم بعدها Mapping sign-off وDry Run على Staging ومصالحة وتوقيع ملاك البيانات وFinance.

## أدلة الاختبار

توجد اختبارات تلقائية لملف صحيح، وللتكرار والمرجع المفقود والتاريخ الخاطئ والدفعة غير المتزنة، وللسماح بالملفات غير الموجودة كWarnings، ولإنشاء تقريري JSON وMarkdown. تحفظ نتيجة التشغيل الفعلية في سجل CW-150 قبل قبول أي Dry Run.

## Rollback

الأداة لا تغير Odoo. يمكن إيقاف استخدامها أو revert للـcommit دون أي ترحيل بيانات أو أثر محاسبي.
