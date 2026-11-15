# Signing batch 4 (EMS set): rulings applied, 2026-11-12

Owner, Andrew Azelton, 2026-11-12. The formulary and the full report (with each row as re-read from the PDF) stay outside the repository, with the formulary; this record gives the packet's entry IDs only.

| Outcome | Entries |
|---|---|
| Signed | 22 |
| Failed check (a) or (b) | 6 |
| Flagged in the packet (for individual rulings) | 170 |
| Not expressible by the engine | 9 |
| Non-drug rows (unsigned; not expressible) | 9 |
| **Total** | **216** |

## Signed (22)

| ID | Drug | Population | Route |
|---|---|---|---|
| EMS-001 | Acetaminophen | adult | PO |
| EMS-002 | Acetaminophen | adult | IV/IO |
| EMS-016 | Aspirin | adult | PO |
| EMS-018 | Atropine | adult | IV/IO |
| EMS-019 | Atropine | adult | IM |
| EMS-020 | Atropine | adult | IV/IO |
| EMS-076 | Epinephrine | adult | IM |
| EMS-077 | Epinephrine | adult | NEB |
| EMS-080 | Epinephrine | adult | NEB |
| EMS-089 | Epinephrine | peds | NEB |
| EMS-126 | Ketamine | adult | IM |
| EMS-138 | Lidocaine | adult | IV/IO |
| EMS-139 | Lidocaine | adult | IV/IO |
| EMS-142 | Lidocaine | peds | IV/IO |
| EMS-181 | Norepinephrine | adult | IV/IO |
| EMS-182 | Norepinephrine | adult | IV/IO |
| EMS-187 | Ondansetron | adult | IM |
| EMS-188 | Ondansetron | adult | IV/IO |
| EMS-192 | Oral Glucose | adult | PO |
| EMS-210 | Tranexamic Acid | adult | IN |
| EMS-214 | Tranexamic Acid | peds | IN |
| EMS-216 | Tranexamic Acid | peds | IV/IO |

## Failed check (a) or (b): not signed

| ID | Drug | Population | Route | Why |
|---|---|---|---|---|
| EMS-017 | Atropine | adult | IM | (a) not re-read in the row: route |
| EMS-051 | Dextrose (D10W) | peds | IV/IO | (a) not re-read in the row: max |
| EMS-128 | Ketamine | adult | IM | (a) not re-read in the row: route |
| EMS-186 | Ondansetron | adult | PO | (a) not re-read in the row: route, unit |
| EMS-211 | Tranexamic Acid | adult | NEB | (a) not re-read in the row: dose, unit |
| EMS-215 | Tranexamic Acid | peds | NEB | (a) not re-read in the row: unit |

## Not expressible by the engine: not signed

| ID | Drug | Population | Route | Why |
|---|---|---|---|---|
| EMS-052 | Dextrose (D10W) | peds | IV/IO | no indication class |
| EMS-079 | Epinephrine | adult | Topical | route not served (SL, topical, IO only) |
| EMS-136 | Lidocaine | adult | Topical | route not served (SL, topical, IO only) |
| EMS-137 | Lidocaine | adult | IO | route not served (SL, topical, IO only) |
| EMS-202 | Sodium Bicarbonate | adult | NEB | dose is not one g/mg/mcg amount (bands, mEq, two doses); max not expressible |
| EMS-207 | Sodium Bicarbonate | peds | IV/IO | dose is not one g/mg/mcg amount (bands, mEq, two doses); max not expressible |
| EMS-208 | Sodium Bicarbonate | peds | IV/IO | dose is not one g/mg/mcg amount (bands, mEq, two doses); max not expressible |
| EMS-209 | Tranexamic Acid | adult | Topical | route not served (SL, topical, IO only) |
| EMS-213 | Tranexamic Acid | peds | Topical | route not served (SL, topical, IO only) |

## Non-drug rows: the engine cannot express them, so they stay unsigned

| ID | Drug | Population | Route | Why |
|---|---|---|---|---|
| EMS-025 | Blood Products | adult | IV/IO | units are not g, mg or mcg |
| EMS-026 | Blood Products | peds | IV/IO | units are not g, mg or mcg |
| EMS-121 | Isotonic Crystalloid Fluids | adult | NEB | units are not g, mg or mcg |
| EMS-122 | Isotonic Crystalloid Fluids | peds | NEB | units are not g, mg or mcg |
| EMS-123 | Isotonic Crystalloid Fluids | adult | IV/IO | units are not g, mg or mcg |
| EMS-124 | Isotonic Crystalloid Fluids | peds | IV/IO | units are not g, mg or mcg |
| EMS-194 | Oxygen | adult | Inhaled | units are not g, mg or mcg |
| EMS-195 | Oxygen | peds | Inhaled | units are not g, mg or mcg |
| EMS-196 | Oxygen | peds | Inhaled | units are not g, mg or mcg |

## Flagged in the packet: not signed, for individual rulings

| ID | Drug | Population | Route | Why |
|---|---|---|---|---|
| EMS-003 | Acetaminophen | peds | PO | layout or content flag on the page |
| EMS-004 | Acetaminophen | peds | IV/IO | layout or content flag on the page |
| EMS-005 | Adenosine | adult | IV/IO | layout or content flag on the page |
| EMS-006 | Adenosine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-007 | Albuterol | adult | Inhaled (MDI) | contraindication/adverse column flag |
| EMS-008 | Albuterol | adult | NEB | contraindication/adverse column flag |
| EMS-009 | Albuterol | adult | NEB | contraindication/adverse column flag |
| EMS-010 | Albuterol | peds | NEB | contraindication/adverse column flag |
| EMS-011 | Amiodarone | adult | IV/IO | contraindication/adverse column flag |
| EMS-012 | Amiodarone | adult | IV/IO | contraindication/adverse column flag |
| EMS-013 | Amiodarone | adult | IV/IO | contraindication/adverse column flag |
| EMS-014 | Amiodarone | peds | IV/IO | contraindication/adverse column flag |
| EMS-015 | Amiodarone | peds | IV/IO | contraindication/adverse column flag |
| EMS-021 | Atropine | peds | IM | layout or content flag on the page |
| EMS-022 | Atropine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-023 | Atropine | peds | IM | layout or content flag on the page |
| EMS-024 | Atropine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-027 | Buprenorphine | adult | PO | layout or content flag on the page |
| EMS-028 | Buprenorphine | adult | PO | layout or content flag on the page |
| EMS-029 | Buprenorphine | adult | PO | layout or content flag on the page |
| EMS-030 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-031 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-032 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-033 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-034 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-035 | Calcium Chloride | adult | IV/IO | layout or content flag on the page |
| EMS-036 | Calcium Chloride | peds | IV/IO | layout or content flag on the page |
| EMS-037 | Calcium Chloride | peds | IV/IO | layout or content flag on the page |
| EMS-038 | Dexamethasone | adult | IV/IO | layout or content flag on the page |
| EMS-039 | Dexamethasone | adult | IM | layout or content flag on the page |
| EMS-040 | Dexamethasone | adult | PO | layout or content flag on the page |
| EMS-041 | Dexamethasone | adult | IV/IO | layout or content flag on the page |
| EMS-042 | Dexamethasone | adult | IM | layout or content flag on the page |
| EMS-043 | Dexamethasone | adult | PO | layout or content flag on the page |
| EMS-044 | Dexamethasone | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-045 | Dexamethasone | peds | IM | weight-table cell outside the dose per kg |
| EMS-046 | Dexamethasone | peds | PO | weight-table cell outside the dose per kg |
| EMS-047 | Dexamethasone | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-048 | Dexamethasone | peds | IM | weight-table cell outside the dose per kg |
| EMS-049 | Dexamethasone | peds | PO | weight-table cell outside the dose per kg |
| EMS-050 | Dextrose (D10W) | adult | IV/IO | layout or content flag on the page |
| EMS-053 | Diltiazem | adult | IV/IO | layout or content flag on the page |
| EMS-054 | Diltiazem | adult | IV/IO | layout or content flag on the page |
| EMS-055 | Diphenhydramine | adult | PO | contraindication/adverse column flag |
| EMS-056 | Diphenhydramine | adult | IV/IO | contraindication/adverse column flag |
| EMS-057 | Diphenhydramine | adult | IM | contraindication/adverse column flag |
| EMS-058 | Diphenhydramine | adult | IV/IO | contraindication/adverse column flag |
| EMS-059 | Diphenhydramine | adult | IM | contraindication/adverse column flag |
| EMS-060 | Diphenhydramine | adult | IV/IO | contraindication/adverse column flag |
| EMS-061 | Diphenhydramine | adult | IM | contraindication/adverse column flag |
| EMS-062 | Diphenhydramine | peds | IV/IO | contraindication/adverse column flag |
| EMS-063 | Diphenhydramine | peds | IM | contraindication/adverse column flag |
| EMS-064 | Diphenhydramine | peds | IV/IO | contraindication/adverse column flag |
| EMS-065 | Diphenhydramine | peds | IM | contraindication/adverse column flag |
| EMS-066 | Diphenhydramine | peds | PO | table-only dose |
| EMS-067 | Droperidol | adult | IV/IO | layout or content flag on the page |
| EMS-068 | Droperidol | adult | IM | layout or content flag on the page |
| EMS-069 | Droperidol | adult | IV/IO | layout or content flag on the page |
| EMS-070 | Droperidol | adult | IM | layout or content flag on the page |
| EMS-071 | Droperidol | adult | IV/IO | layout or content flag on the page |
| EMS-072 | Droperidol | adult | IM | layout or content flag on the page |
| EMS-073 | Epinephrine | adult | IV/IO | layout or content flag on the page |
| EMS-074 | Epinephrine | adult | IV/IO | layout or content flag on the page |
| EMS-075 | Epinephrine | adult | IV/IO | layout or content flag on the page |
| EMS-078 | Epinephrine | adult | IV/IO | layout or content flag on the page |
| EMS-081 | Epinephrine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-082 | Epinephrine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-083 | Epinephrine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-084 | Epinephrine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-085 | Epinephrine | peds | IM | weight-table cell outside the dose per kg |
| EMS-086 | Epinephrine | peds | IM | weight-table cell outside the dose per kg |
| EMS-087 | Epinephrine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-088 | Epinephrine | peds | IM | weight-table cell outside the dose per kg |
| EMS-090 | Fentanyl | adult | IV/IO | contraindication/adverse column flag |
| EMS-091 | Fentanyl | adult | IM | contraindication/adverse column flag |
| EMS-092 | Fentanyl | adult | IN | contraindication/adverse column flag |
| EMS-093 | Fentanyl | adult | IV/IO | contraindication/adverse column flag |
| EMS-094 | Fentanyl | adult | IM | contraindication/adverse column flag |
| EMS-095 | Fentanyl | adult | IN | contraindication/adverse column flag |
| EMS-096 | Fentanyl | adult | IV/IO | contraindication/adverse column flag |
| EMS-097 | Fentanyl | adult | IM | contraindication/adverse column flag |
| EMS-098 | Fentanyl | adult | IN | contraindication/adverse column flag |
| EMS-099 | Fentanyl | adult | IV/IO | contraindication/adverse column flag |
| EMS-100 | Fentanyl | adult | IM | contraindication/adverse column flag |
| EMS-101 | Fentanyl | adult | IN | contraindication/adverse column flag |
| EMS-102 | Fentanyl | peds | IN | contraindication/adverse column flag |
| EMS-103 | Fentanyl | peds | IV/IO | contraindication/adverse column flag |
| EMS-104 | Fentanyl | peds | IM | contraindication/adverse column flag |
| EMS-105 | Fentanyl | peds | IV/IO | contraindication/adverse column flag |
| EMS-106 | Fentanyl | peds | IM | contraindication/adverse column flag |
| EMS-107 | Fentanyl | peds | IV/IO | contraindication/adverse column flag |
| EMS-108 | Fentanyl | peds | IM | contraindication/adverse column flag |
| EMS-109 | Glucagon | adult | IM | layout or content flag on the page |
| EMS-110 | Glucagon | adult | IV/IO | layout or content flag on the page |
| EMS-111 | Glucagon | peds | IM | layout or content flag on the page |
| EMS-112 | Glucagon | peds | IV/IO | layout or content flag on the page |
| EMS-113 | Hydroxocobalamin (CyanoKit) | adult | IV/IO | layout or content flag on the page |
| EMS-114 | Hydroxocobalamin (CyanoKit) | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-115 | Ibuprofen | adult | PO | layout or content flag on the page |
| EMS-116 | Ibuprofen | adult | PO | layout or content flag on the page |
| EMS-117 | Ipratropium Bromide (Atrovent) | adult | NEB | contraindication/adverse column flag |
| EMS-118 | Ipratropium Bromide (Atrovent) | adult | NEB | contraindication/adverse column flag |
| EMS-119 | Ipratropium Bromide (Atrovent) | peds | NEB | contraindication/adverse column flag |
| EMS-120 | Ipratropium Bromide (Atrovent) | peds | NEB | contraindication/adverse column flag |
| EMS-125 | Ketamine | adult | IV/IO | layout or content flag on the page |
| EMS-127 | Ketamine | adult | IM | layout or content flag on the page |
| EMS-129 | Ketamine | adult | IV/IO | layout or content flag on the page |
| EMS-130 | Ketamine | adult | IV/IO | layout or content flag on the page |
| EMS-131 | Ketamine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-132 | Ketamine | peds | IM | weight-table cell outside the dose per kg |
| EMS-133 | Ketamine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-134 | Ketamine | peds | IM | weight-table cell outside the dose per kg |
| EMS-135 | Ketamine | peds | IV/IO | weight-table cell outside the dose per kg |
| EMS-140 | Lidocaine | peds | Topical | layout or content flag on the page |
| EMS-141 | Lidocaine | peds | IO | weight-table cell outside the dose per kg |
| EMS-143 | Magnesium Sulfate 50% | adult | IV/IO | layout or content flag on the page |
| EMS-144 | Magnesium Sulfate 50% | adult | IV/IO | layout or content flag on the page |
| EMS-145 | Magnesium Sulfate 50% | adult | IV/IO | layout or content flag on the page |
| EMS-146 | Magnesium Sulfate 50% | adult | IV/IO | layout or content flag on the page |
| EMS-147 | Magnesium Sulfate 50% | adult | IV/IO | layout or content flag on the page |
| EMS-148 | Magnesium Sulfate 50% | peds | IV/IO | layout or content flag on the page |
| EMS-149 | Magnesium Sulfate 50% | peds | IV/IO | layout or content flag on the page |
| EMS-150 | Magnesium Sulfate 50% | peds | IV/IO | layout or content flag on the page |
| EMS-151 | Magnesium Sulfate 50% | peds | IV/IO | layout or content flag on the page |
| EMS-152 | Midazolam | adult | IV/IO | contraindication/adverse column flag |
| EMS-153 | Midazolam | adult | IM | contraindication/adverse column flag |
| EMS-154 | Midazolam | adult | IN | contraindication/adverse column flag |
| EMS-155 | Midazolam | adult | IV/IO | contraindication/adverse column flag |
| EMS-156 | Midazolam | adult | IM | contraindication/adverse column flag |
| EMS-157 | Midazolam | adult | IN | contraindication/adverse column flag |
| EMS-158 | Midazolam | adult | IV/IO | contraindication/adverse column flag |
| EMS-159 | Midazolam | adult | IM | contraindication/adverse column flag |
| EMS-160 | Midazolam | adult | IN | contraindication/adverse column flag |
| EMS-161 | Midazolam | adult | IV/IO | contraindication/adverse column flag |
| EMS-162 | Midazolam | adult | IM | contraindication/adverse column flag |
| EMS-163 | Midazolam | adult | IN | contraindication/adverse column flag |
| EMS-164 | Midazolam | adult | IV/IO | contraindication/adverse column flag |
| EMS-165 | Midazolam | peds | IV/IO | contraindication/adverse column flag |
| EMS-166 | Midazolam | peds | IM | contraindication/adverse column flag |
| EMS-167 | Midazolam | peds | IN | contraindication/adverse column flag |
| EMS-168 | Midazolam | peds | IV/IO | contraindication/adverse column flag |
| EMS-169 | Naloxone | adult | IN | card watermarked DRAFT |
| EMS-170 | Naloxone | adult | IN | card watermarked DRAFT |
| EMS-171 | Naloxone | adult | IM | card watermarked DRAFT |
| EMS-172 | Naloxone | adult | IV/IO | card watermarked DRAFT |
| EMS-173 | Naloxone | peds | IN | card watermarked DRAFT |
| EMS-174 | Naloxone | peds | IM | card watermarked DRAFT |
| EMS-175 | Naloxone | peds | IV/IO | card watermarked DRAFT |
| EMS-176 | Nitroglycerin | adult | SL | layout or content flag on the page |
| EMS-177 | Nitroglycerin | adult | Topical | layout or content flag on the page |
| EMS-178 | Nitroglycerin | adult | SL | layout or content flag on the page |
| EMS-179 | Nitroglycerin | adult | Topical | layout or content flag on the page |
| EMS-180 | Nitroglycerin | adult | SL | layout or content flag on the page |
| EMS-183 | Norepinephrine | peds | IV/IO | layout or content flag on the page |
| EMS-184 | Olanzapine (Zyprexa) | adult | SL | contraindication/adverse column flag |
| EMS-185 | Olanzapine (Zyprexa) | adult | SL | contraindication/adverse column flag |
| EMS-189 | Ondansetron | peds | PO | layout or content flag on the page |
| EMS-190 | Ondansetron | peds | IM | layout or content flag on the page |
| EMS-191 | Ondansetron | peds | IV/IO | layout or content flag on the page |
| EMS-193 | Oral Glucose | peds | PO | layout or content flag on the page |
| EMS-197 | Pralidoxime | adult | IM | layout or content flag on the page |
| EMS-198 | Pralidoxime | adult | IM | layout or content flag on the page |
| EMS-199 | Pralidoxime | peds | IM | weight-table cell outside the dose per kg |
| EMS-200 | Rocuronium Bromide | adult | IV/IO | contraindication/adverse column flag |
| EMS-201 | Rocuronium Bromide | adult | IV/IO | contraindication/adverse column flag |
| EMS-203 | Sodium Bicarbonate | adult | IV/IO | layout or content flag on the page |
| EMS-204 | Sodium Bicarbonate | adult | IV/IO | layout or content flag on the page |
| EMS-205 | Sodium Bicarbonate | adult | IV/IO | layout or content flag on the page |
| EMS-206 | Sodium Bicarbonate | adult | IV/IO | layout or content flag on the page |
| EMS-212 | Tranexamic Acid | adult | IV/IO | layout or content flag on the page |

## Checks (a) and (b) on every drug entry, flagged or not

Check (a) ran on 185 entries (the rest have no single g/mg/mcg dose to re-read) and failed on 50. Check (b) ran on 62 paediatric entries with a weight table and failed on 28.

### Check (a) failures

- EMS-013 Amiodarone · adult IV/IO: not found in the row as re-read: dose, route, unit
- EMS-015 Amiodarone · peds IV/IO: not found in the row as re-read: '/kg', dose, route
- EMS-017 Atropine · adult IM: not found in the row as re-read: route
- EMS-027 Buprenorphine · adult PO: not found in the row as re-read: route
- EMS-031 Calcium Chloride · adult IV/IO: not found in the row as re-read: route
- EMS-032 Calcium Chloride · adult IV/IO: not found in the row as re-read: route
- EMS-035 Calcium Chloride · adult IV/IO: not found in the row as re-read: dose, route, unit
- EMS-044 Dexamethasone · peds IV/IO: not found in the row as re-read: max
- EMS-045 Dexamethasone · peds IM: not found in the row as re-read: max
- EMS-046 Dexamethasone · peds PO: not found in the row as re-read: max
- EMS-051 Dextrose (D10W) · peds IV/IO: not found in the row as re-read: max
- EMS-058 Diphenhydramine · adult IV/IO: not found in the row as re-read: dose, route, unit
- EMS-059 Diphenhydramine · adult IM: not found in the row as re-read: dose, route, unit
- EMS-060 Diphenhydramine · adult IV/IO: not found in the row as re-read: dose, route, unit
- EMS-061 Diphenhydramine · adult IM: not found in the row as re-read: dose, route, unit
- EMS-064 Diphenhydramine · peds IV/IO: not found in the row as re-read: '/kg', dose
- EMS-065 Diphenhydramine · peds IM: not found in the row as re-read: '/kg', dose
- EMS-066 Diphenhydramine · peds PO: not found in the row as re-read: '/kg', dose, unit
- EMS-067 Droperidol · adult IV/IO: not found in the row as re-read: route
- EMS-068 Droperidol · adult IM: not found in the row as re-read: route
- EMS-086 Epinephrine · peds IM: not found in the row as re-read: max
- EMS-096 Fentanyl · adult IV/IO: not found in the row as re-read: dose
- EMS-097 Fentanyl · adult IM: not found in the row as re-read: dose
- EMS-098 Fentanyl · adult IN: not found in the row as re-read: dose
- EMS-099 Fentanyl · adult IV/IO: not found in the row as re-read: dose, route
- EMS-100 Fentanyl · adult IM: not found in the row as re-read: dose, route
- EMS-101 Fentanyl · adult IN: not found in the row as re-read: dose, route
- EMS-112 Glucagon · peds IV/IO: not found in the row as re-read: '/kg', dose, max, unit
- EMS-118 Ipratropium Bromide (Atrovent) · adult NEB: not found in the row as re-read: dose, route, unit
- EMS-120 Ipratropium Bromide (Atrovent) · peds NEB: not found in the row as re-read: dose, route, unit
- EMS-127 Ketamine · adult IM: not found in the row as re-read: route
- EMS-128 Ketamine · adult IM: not found in the row as re-read: route
- EMS-143 Magnesium Sulfate 50% · adult IV/IO: not found in the row as re-read: dose, unit
- EMS-144 Magnesium Sulfate 50% · adult IV/IO: not found in the row as re-read: route
- EMS-145 Magnesium Sulfate 50% · adult IV/IO: not found in the row as re-read: route
- EMS-147 Magnesium Sulfate 50% · adult IV/IO: not found in the row as re-read: route
- EMS-148 Magnesium Sulfate 50% · peds IV/IO: not found in the row as re-read: max
- EMS-150 Magnesium Sulfate 50% · peds IV/IO: not found in the row as re-read: '/kg', dose, unit
- EMS-151 Magnesium Sulfate 50% · peds IV/IO: not found in the row as re-read: '/kg', dose, max, unit
- EMS-171 Naloxone · adult IM: not found in the row as re-read: route
- EMS-172 Naloxone · adult IV/IO: not found in the row as re-read: route
- EMS-174 Naloxone · peds IM: not found in the row as re-read: route
- EMS-175 Naloxone · peds IV/IO: not found in the row as re-read: route
- EMS-178 Nitroglycerin · adult SL: not found in the row as re-read: dose, route, unit
- EMS-185 Olanzapine (Zyprexa) · adult SL: not found in the row as re-read: route
- EMS-186 Ondansetron · adult PO: not found in the row as re-read: route, unit
- EMS-200 Rocuronium Bromide · adult IV/IO: not found in the row as re-read: route
- EMS-201 Rocuronium Bromide · adult IV/IO: not found in the row as re-read: route
- EMS-211 Tranexamic Acid · adult NEB: not found in the row as re-read: dose, unit
- EMS-215 Tranexamic Acid · peds NEB: not found in the row as re-read: '/kg', unit

### Check (b) failures

- EMS-003 Acetaminophen · peds PO: the weight table has no dose per kg or concentration to check against
- EMS-004 Acetaminophen · peds IV/IO: 2 kgs: No IV dose — no dose printed for this band; 4kgs: No IV dose — no dose printed for this band; 6 kgs: No IV dose — no dose printed for this band; 8-9 kgs: No IV dose — no dose printed for this band
- EMS-024 Atropine · peds IV/IO: 30-36 kgs: printed 1.3 mL; dose per kg × weight ÷ 0.4 gives 1.5–1.8 mL (rounding ±0.05)
- EMS-062 Diphenhydramine · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-063 Diphenhydramine · peds IM: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-064 Diphenhydramine · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-065 Diphenhydramine · peds IM: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-081 Epinephrine · peds IV/IO: 500g: printed 0.5mL; dose per kg × weight ÷ 0.1 gives 0.05–0.05 mL (rounding ±0.05)
- EMS-082 Epinephrine · peds IV/IO: 500g: printed 0.5mL; dose per kg × weight ÷ 0.1 gives 0.05–0.05 mL (rounding ±0.05)
- EMS-086 Epinephrine · peds IM: 500g: None — no dose printed for this band; 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band; 6 kgs: None — no dose printed for this band
- EMS-088 Epinephrine · peds IM: 500g: None — no dose printed for this band; 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band; 6 kgs: None — no dose printed for this band
- EMS-103 Fentanyl · peds IV/IO: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-104 Fentanyl · peds IM: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-105 Fentanyl · peds IV/IO: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-106 Fentanyl · peds IM: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-107 Fentanyl · peds IV/IO: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-108 Fentanyl · peds IM: 6 kgs: printed 0.08 ml; dose per kg × weight ÷ 50 gives 0.12–0.12 mL (rounding ±0.005)
- EMS-114 Hydroxocobalamin (CyanoKit) · peds IV/IO: 2 kgs: printed 8.4 mL; dose per kg × weight ÷ 25 gives 5.6–5.6 mL (rounding ±0.05); 17-19 kgs: printed 46 mL; dose per kg × weight ÷ 25 gives 47.6–53.2 mL (rounding ±0.5)
- EMS-131 Ketamine · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band; 6 kgs: None — no dose printed for this band; 8-9 kgs: None — no dose printed for this band; 10-11 kgs: None — no dose printed for this band; 12-14 kgs: None — no dose printed for this band; 15-16 kgs: None — no dose printed for this band; 17-19 kgs: None — no dose printed for this band; 20-23 kgs: None — no dose printed for this band
- EMS-134 Ketamine · peds IM: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band; 6 kgs: None — no dose printed for this band; 8-9 kgs: None — no dose printed for this band; 10-11 kgs: None — no dose printed for this band; 12-14 kgs: printed 0.4 mL; dose per kg × weight ÷ 100 gives 0.48–0.56 mL (rounding ±0.05); 15-16 kgs: printed 0.8 mL; dose per kg × weight ÷ 100 gives 0.6–0.64 mL (rounding ±0.05)
- EMS-165 Midazolam · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-166 Midazolam · peds IM: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-167 Midazolam · peds IN: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-168 Midazolam · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-189 Ondansetron · peds PO: the weight table has no dose per kg or concentration to check against
- EMS-190 Ondansetron · peds IM: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-191 Ondansetron · peds IV/IO: 2 kgs: None — no dose printed for this band; 4kgs: None — no dose printed for this band
- EMS-199 Pralidoxime · peds IM: 20-23 kgs: printed 8 mL; dose per kg × weight ÷ 50 gives 6–6.9 mL (rounding ±0.5)
