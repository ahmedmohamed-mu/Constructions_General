# MU Construction Variations, Claims and EOT

DEV-110 commercial change control for Odoo 19.

## Scope

- Potential Change Events linked to project, contract, RFI, drawing, BOQ, WBS and location.
- Contractual notices with deadline activities, review, issue and acknowledgement controls.
- Variation estimate lines covering material, labor, equipment, subcontract, overhead, time-related cost and markup.
- Separate pending forecast, submitted, negotiated and approved values.
- Claims and EOT with notice compliance, contemporary records, affected activities, schedule references and client decisions.
- Contract rollups for approved/pending variations, approved/pending claims, revised value and approved EOT.
- Controlled draft budget amendment from an approved variation; the current baseline remains effective until the amendment is approved.

## Safety boundaries

- Pending or rejected variations and claims never change approved contract totals.
- Original BOQ lines are never edited by a variation.
- Approved or rejected commercial records and estimate lines are locked.
- The module creates no invoices, journal entries, payments, stock moves or ETA submissions.
- Approval roles and notice lead time come from effective company/project profiles.

