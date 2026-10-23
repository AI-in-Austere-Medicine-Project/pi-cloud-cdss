# Vent card settings, for the owner's signature ruling (2026-10-22)

Owner, 2026-10-22 (v5.1.0 freeze): "vent card settings printed for my signature ruling".

**Why:** the A35 sweep found that the five physiology vent cards serve today with `signoff: true`, but their signer is `reviewed_by: "clinician"` (2026-08-22), a role and not a name. Every setting they print is a number no named signer has signed.

**What this packet is:**
- Every line each card can render, verbatim from `server/vent_cards.json`, with the card's references. Lines containing a number are marked **#**.
- The ideal-body-weight constants the tidal volume is computed with, which are hardcoded in `server/vent_module.py` and uncited.

**Not covered:** `vent_devices.json` and `vent_troubleshooting.json`. They are unsigned (`PENDING_CLINICAL_SIGNOFF`) and render nothing.

**Nothing is signed or changed by this packet.** For each card, rule one of:
- **SIGN**: Andrew Azelton signs the card as printed.
- **CHANGE**: name the line and the new text.
- **REMOVE**: name the line; it is taken off the card.
- **UNSIGN**: the card stops serving, and vent questions for that physiology hold.

Each ruling is applied in its own commit after it is given.

## Lung-protective baseline (`lung_protective_baseline`)

Current signoff: `signoff: true`, reviewed_by "clinician", 2026-08-22, version 1.0.0.

Served when the question says one of: ards, ardsnet, lung protective, lung-protective, acute respiratory distress.

**Initial settings**

- mode: Volume control (PRVC)
- vt_ml_per_kg_ibw: **#** 6 (× the patient's ideal body weight, or actual weight with no height)
- rate_strategy: **#** Start RR 16-20 for minute ventilation at 6 mL/kg; titrate to pH/EtCO2, permissive hypercapnia acceptable (pH >= 7.20).
- peep: **#** ARDSNet low-PEEP/FiO2 ladder — start 5-8, climb with FiO2 need
- fio2: **#** start 100% if acute, down the ladder to lowest FiO2 holding SpO2 >= 94%

**Titrate**

- **#** Plateau < 30 — reduce VT toward 4 mL/kg if exceeded
- Oxygenation — climb PEEP/FiO2 ladder together
- **#** pH — permissive hypercapnia to >= 7.20 before increasing VT

**Watch for**

- **#** Plateau > 30
- **#** Driving pressure (plateau minus PEEP) > 15
- Rising FiO2 requirement = worsening shunt
- Breath stacking / dyssynchrony

**Evac if**

- Refractory hypoxaemia despite optimised PEEP/FiO2
- Plateau/driving pressure uncontrollable at protective VT
- Rising pressor requirement with the respiratory failure

**Caveat / assumes**

- actual_weight_caveat: No height on file — this tidal volume came off actual body weight, which runs high. Enter a height to dose on ideal body weight; until then treat the VT as a ceiling and watch plateau pressure.
- escape_hatch: General lung-protective/ARDS-pattern card. If the driver is a specific physiology — metabolic acidosis, obstruction, TBI, chest trauma — use that card. Assumes VT on height-derived IBW, not actual weight.

**TLDR**

- **#** 6 mL/kg IBW, plateau under 30, permissive hypercapnia to pH 7.2.

**References (as written on the card)**

- ARDSNet/NHLBI ARDS Network low-tidal-volume protocol

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 

## Metabolic acidosis — compensation preserved (`metabolic_acidosis`)

Current signoff: `signoff: true`, reviewed_by "clinician", 2026-08-22, version 1.0.0.

Served when the question says one of: dka, diabetic ketoacidosis, ketoacidosis, acidosis, acidotic, salicylate, aspirin overdose, septic acidosis, ph 7.1, ph 7.0, ph 6.9, kussmaul, bicarb low.

**Initial settings**

- mode: Volume control (PRVC if available)
- vt_ml_per_kg_ibw: **#** 6 (× the patient's ideal body weight, or actual weight with no height)
- rate_strategy: **#** Match the patient's compensatory minute ventilation — do NOT set a normal rate. Start RR 20-30 and titrate immediately to pre-intubation EtCO2/pH. A patient breathing 35-40 spontaneously was defending their pH; setting 12-16 halves minute ventilation and the pH crashes. Match pre-tube minute ventilation if known; otherwise start high (>=24) and correct up on the first EtCO2/gas.
- peep: **#** 5
- fio2: **#** titrate to SpO2 >= 94%

**Titrate**

- EtCO2/serial pH — keep minute ventilation matching pre-intubation compensation, correct rate up if pH falls
- **#** Plateau < 30 — if high rate drives plateau up, accept higher EtCO2 before sacrificing lung protection and escalate
- FiO2 down as SpO2 allows

**Watch for**

- Falling pH / rising EtCO2 in the minutes after intubation = under-ventilating a compensating patient
- Peri-intubation cardiac arrest — highest-risk moment in severe acidosis
- Breath stacking if high rate leaves inadequate expiratory time
- **#** Plateau climbing above 30

**Evac if**

- pH keeps falling despite matched/maximised safe minute ventilation
- Cannot achieve required minute ventilation within safe plateau pressure
- Haemodynamic collapse peri- or post-intubation

**Caveat / assumes**

- actual_weight_caveat: No height on file — this tidal volume came off actual body weight, which runs high. Enter a height to dose on ideal body weight; until then treat the VT as a ceiling and watch plateau pressure.
- escape_hatch: Assumes metabolic acidosis with preserved respiratory compensation (DKA, salicylate, sepsis, severe diarrhoea). Does NOT apply to respiratory/mixed acidosis or ARDS-pattern lungs — use the lung-protective card. Correcting the underlying cause is definitive; the vent only buys time.

**TLDR**

- **#** Match their fast breathing — start RR 20-30, never a normal rate, or the pH crashes.

**References (as written on the card)**

- ARDSNet/NHLBI ARDS Network low-tidal-volume protocol
- REBEL EM Simplifying Mechanical Ventilation Part 3 Severe Metabolic Acidosis 2024
- Air Medical Journal VAPOX for DKA case series 2025
- Weingart & Levitan peri-intubation physiology

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 

## Obstructive — asthma and COPD (`obstructive`)

Current signoff: `signoff: true`, reviewed_by "clinician", 2026-08-22, version 1.0.0.

Served when the question says one of: asthma, asthmatic, copd, obstructive, wheezing, bronchospasm, air trapping, status asthmaticus.

**Initial settings**

- mode: Volume control
- vt_ml_per_kg_ibw: **#** 6 (× the patient's ideal body weight, or actual weight with no height)
- rate_strategy: **#** LOW rate — start RR 8-12 to allow long expiratory time and prevent breath stacking/auto-PEEP. Opposite of the metabolic-acidosis card. Accept high EtCO2; permissive hypercapnia (pH >= 7.20) beats dynamic hyperinflation. Prolong expiration — target I:E 1:4 or longer.
- peep: **#** low — start 0-5; extrinsic PEEP can worsen auto-PEEP, keep minimal
- fio2: **#** titrate to SpO2 >= 94%

**Titrate**

- Expiratory time / auto-PEEP — lengthen expiration, drop rate, until flow returns to zero before the next breath
- **#** Plateau < 30
- pH — permissive hypercapnia, treat the bronchospasm don't chase CO2 with the vent

**Watch for**

- Breath stacking / auto-PEEP — flow doesn't return to baseline, rising plateau, hypotension
- Sudden hypotension or arrest after intubation = dynamic hyperinflation — DISCONNECT the circuit and let them exhale fully then resume at a lower rate
- Rising peak (bronchospasm) vs rising plateau (hyperinflation) are different problems
- Barotrauma / pneumothorax risk

**Evac if**

- **#** Refractory hypercapnia with pH < 7.20 despite optimisation
- Recurrent auto-PEEP/hyperinflation not controlled by rate reduction
- Pneumothorax or haemodynamic instability

**Caveat / assumes**

- actual_weight_caveat: No height on file — this tidal volume came off actual body weight, which runs high. Enter a height to dose on ideal body weight; until then treat the VT as a ceiling and watch plateau pressure.
- escape_hatch: Assumes severe obstructive physiology (status asthmaticus, severe COPD). Disconnect-to-exhale is specific to hyperinflation — if collapse is from tension pneumothorax that is a different emergency (decompression). Continue aggressive bronchodilator/steroid therapy; the vent is supportive.

**TLDR**

- **#** Slow rate (8-12), long exhale, accept high CO2 — disconnect if they crash.

**References (as written on the card)**

- StatPearls Status Asthmaticus 2025
- Medscape Status Asthmaticus Treatment & Management
- Deranged Physiology Ventilation strategies for status asthmaticus
- LITFL permissive hypercapnia and disconnect maneuver

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 

## Traumatic brain injury (`tbi`)

Current signoff: `signoff: true`, reviewed_by "clinician", 2026-08-22, version 1.0.0.

Served when the question says one of: tbi, traumatic brain injury, head injury, gcs, herniation, icp, intracranial.

**Initial settings**

- mode: Volume control (PRVC)
- vt_ml_per_kg_ibw: **#** 6 (× the patient's ideal body weight, or actual weight with no height)
- rate_strategy: **#** Target normocapnia — EtCO2 35-40 / PaCO2 35-45. Start RR 16-20, titrate to EtCO2. Do NOT routinely hyperventilate — prophylactic hypocapnia causes cerebral ischaemia. Brief hyperventilation to EtCO2 30-35 is a TEMPORARY rescue for impending herniation only, then return to normocapnia.
- peep: **#** 5
- fio2: **#** titrate to SpO2 >= 94% — avoid hypoxia absolutely

**Titrate**

- **#** EtCO2 35-40 (normocapnia) — the core rule
- **#** SpO2 >= 94% — never tolerate hypoxia
- Support MAP/SBP for cerebral perfusion

**Watch for**

- **#** Hypoxia (SpO2 < 90%) and hypotension each independently worsen TBI outcome
- **#** Maintain SBP >= 110 mmHg (adult TBI) — the single SBP target for this card, treat hypotension aggressively
- **#** Inadvertent hyperventilation (EtCO2 < 35) outside a herniation rescue
- Herniation signs blown pupil posturing Cushing response

**Evac if**

- Signs of herniation — expedite neurosurgical evacuation, brief hyperventilation bridge only
- **#** Cannot maintain SpO2 >= 94% or SBP >= 110
- GCS deterioration

**Caveat / assumes**

- actual_weight_caveat: No height on file — this tidal volume came off actual body weight, which runs high. Enter a height to dose on ideal body weight; until then treat the VT as a ceiling and watch plateau pressure.
- escape_hatch: Assumes isolated/predominant TBI. Polytrauma with haemorrhagic shock changes priorities — resuscitate pressure first. If chest trauma coexists, cross-check the chest-trauma card. Herniation hyperventilation is a temporary bridge, not a setting.

**TLDR**

- **#** Normocapnia (EtCO2 35-40), SpO2 >= 94%, SBP >= 110 — don't hyperventilate unless herniating.

**References (as written on the card)**

- Brain Trauma Foundation Guidelines for Severe TBI 4th ed
- ACS TBI Best Practices 2024 SBP >= 110
- JTS TBI/PFC CPG EtCO2 35-45 SpO2 >93%
- Emergency Neurological Life Support ENLS 6.0 TBI

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 

## Chest trauma (`chest_trauma`)

Current signoff: `signoff: true`, reviewed_by "clinician", 2026-08-22, version 1.0.0.

Served when the question says one of: chest trauma, blast lung, pulmonary contusion, flail, flail chest, hemothorax, pneumothorax, chest injury, penetrating chest.

**Initial settings**

- mode: Volume control (PRVC)
- vt_ml_per_kg_ibw: **#** 6 (× the patient's ideal body weight, or actual weight with no height)
- rate_strategy: **#** Start RR 16-20 for normal minute ventilation; titrate to EtCO2/pH.
- peep: **#** 5 — supports oxygenation of contused lung; be alert positive pressure can convert a simple pneumothorax to tension
- fio2: **#** titrate to SpO2 >= 94% — contusion often needs more

**Titrate**

- **#** SpO2/oxygenation — contusion worsens over 24-48h FiO2/PEEP need may climb
- **#** Plateau < 30
- EtCO2/pH for minute ventilation

**Watch for**

- Positive-pressure ventilation can convert a simple pneumothorax to TENSION — sudden rising peak pressures + hypotension + unilateral absent breath sounds = decompress NOW (needle/finger) do not troubleshoot the vent first
- Pulmonary contusion evolving — worsening hypoxia over hours
- Rising airway pressures subcutaneous emphysema
- Haemodynamic instability = tension pneumo haemothorax or cardiac/great-vessel injury

**Evac if**

- Tension pneumothorax (decompress first then evac)
- Refractory hypoxaemia from contusion
- Signs of massive haemothorax or cardiac injury

**Caveat / assumes**

- actual_weight_caveat: No height on file — this tidal volume came off actual body weight, which runs high. Enter a height to dose on ideal body weight; until then treat the VT as a ceiling and watch plateau pressure.
- escape_hatch: Assumes blunt/penetrating chest trauma being ventilated. Does NOT override the safety gate's tension-pneumothorax response — if tension physiology is present decompression comes before any ventilator adjustment. For predominant TBI or ARDS-pattern failure use those cards.

**TLDR**

- **#** 6 mL/kg, watch for tension pneumo on positive pressure — decompress before you touch the vent.

**References (as written on the card)**

- JTS Thoracic Trauma CPG
- Standard trauma-ventilation consensus lung-protective VT for pulmonary contusion tension-pneumothorax-on-PPV recognition

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 

## Ideal body weight constants (`server/vent_module.py`)

The tidal volume is VT mL/kg × IBW, using the Devine formula. It falls back to actual weight when no height is on file, and the card says so.

- male base: **#** 50 kg
- female base: **#** 45.5 kg
- per inch over the base height: **#** 2.3 kg
- base height: **#** 60 in

No citation sits beside them.

**Ruling (owner):** SIGN / CHANGE / REMOVE / UNSIGN — 
