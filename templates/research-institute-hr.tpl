name: Research institute / non-profit HR demo
website: https://example.org
company_name: Example Research Institute
country: BE
apps: [hr, hr_recruitment, hr_appraisal, hr_attendance, hr_holidays, hr_payroll,
       hr_referral, hr_skills, planning, approvals, fleet, documents, sign,
       knowledge, survey, calendar, website]
data_size: big
override_model_size: {hr.employee: 150, hr.job: 65, hr.department: 20, hr.applicant: 25, fleet.vehicle: 10}
configuration: |
  HR & operations demo, not a sales one — no crm/sale/purchase/stock.
  Non-profit / research institute with several physical sites (labs, pilot
  lines, workshops), each modeled as an hr.work_location; a handful of
  employees work from home or "other" locations too.
  Departments organized by research program / activity (e.g. circular
  economy, energy transition, materials characterization, digitalisation),
  not by generic Sales/Marketing/IT.
  Job titles are technical/scientific (researcher, PhD researcher, lab
  technician, program leader, activity manager), bilingual FR/EN.
  Recruitment pipeline (hr.recruitment.stage) follows a Belgian-style
  funnel: New -> Initial qualification -> First interview (HR) -> Technical
  interview -> Salary proposal -> Contract proposal -> Hired / Refused-Kept
  in reserve.
  Several working-time regimes on resource.calendar: full-time ~38h/week
  (default), 4/5 ~30.4h/week, half-time ~19h/week. Contract types: CDI
  (default) and CDD (e.g. PhD students, tied to project funding).
  One joint committee / social security classification applies to (almost)
  all employees; payroll is run with Odoo's own Payroll app, not an external
  payroll secretariat connector.
  Approval categories go beyond the generic defaults (Business Trip, Borrow
  Items, Contract Approval, ...) with domain-specific ones: purchase request
  for consumables (workshop/lab), purchase request for equipment above a
  threshold (e.g. > 1000 EUR), access request for restricted areas
  (pilot line / lab), exceptional remote-work request, training request.
  Two related legal entities (res.company) under one group, both Belgian,
  sharing the same defaults (e.g. attendance mode).
