# Needle-decompression procedure for signing (A29, 2026-10-11)

**Status: SIGNED 2026-10-12 by Andrew Azelton (owner), as drafted.** `server/needle_decompression_card.json` carries `signoff: true`, `reviewed_by` and `review_date`; `test_a29_needle_decompression.py` pins the signed text word for word, so a changed line fails until it is re-signed.

**Edition (checked 2026-10-11):** JTS CPG ID74, Wartime Thoracic Injury, **26 Dec 2018, is the current edition.** The live index at jts.health.mil lists it, no newer chest or thoracic CPG supersedes it, and the PDF downloaded from JTS is byte-identical to the corpus copy (SHA-256 `a48c1df8…`). Printed page = PDF page throughout.

**Sources:** ID74 p.5 and p.8 for every line. The WATCH reassessment line also cites **SMOG CY24 p.22** (Chest Trauma; printed page = PDF page), the only corpus passage that states reassessment after needle thoracostomy (owner, 2026-10-11: keep post-decompression reassessment; no SpO2 target written). SMOG is aeromedical-evacuation guidance, and its SpO2 sign on that page reads "(In flight and on O2)". No corpus line names BP and breath sounds as post-decompression checks; ID74 p.5 supports them as the signs that define the condition. Quotes are verbatim from the PDFs' text layer; read them against the printed page before signing.

**What the card is:** the tension-pneumothorax card served since owner ruling 1 (2026-09-24), **word for word**, with each line now tied to its source.

**Before and after signing:** unsigned, a tension presentation is held: "Signs of a tension pneumothorax are recorded, and EdgeCDSS has no signed needle-decompression procedure yet. Decompress per local protocol and contact medical control." (the junctional precedent, owner #139). Signed, the card is served from this file. This pull request should merge only signed.

### DO THIS

**1. Needle decompression now, on the affected side: large bore (14 gauge or larger) 3.25in/8cm catheter in the 4th or 5th intercostal space, anterior axillary line.**
- ID74 p.8: "Clinical suspicion of tension pneumothorax requires rapid treatment, either with needle decompression and subsequent tube thoracostomy, or with immediate tube thoracostomy."
- ID74 p.8: "Needle decompression should be performed with a large bore (14 gauge or larger) 3.25in/8cm catheter in the 4th or 5th intercostal space, anterior axillary line."

**2. Alternate site: 2nd intercostal space, mid-clavicular line (the primary site in children).**
- ID74 p.8: "The alternate needle decompression site is the 2nd intercostal space at the mid-clavicular line (this is the primary site in children)."

**3. Follow with tube thoracostomy as soon as feasible and safe. If it is delayed, be ready to repeat needle decompression.**
- ID74 p.8: "Needle decompression alone is insufficient treatment for a pneumothorax and certainly ineffective for hemothorax and should in most cases be followed by placement of a tube thoracostomy as soon as feasible and safe."
- ID74 p.8: "If tube thoracostomy placement is delayed, providers should be prepared to repeat needle decompression as needed."

### WATCH

**1. Breathing, SpO2, BP and breath sounds after decompression; recurrence.**
- SMOG CY24 p.22: "Goal: SPO2>90%; Improved RR; Equal rise/fall"
- SMOG CY24 p.22: "Needle Thoracostomy may need to be repeated"
- ID74 p.5: "Differentiating between a simple pneumothorax and a tension pneumothorax is based on the presence of hemodynamic effects (hypotension and decreased perfusion) in the latter condition."
- ID74 p.5: "Absent or markedly decreased breath sounds in a patient with known thoracic trauma indicate the need for intervention without additional diagnostic testing."
- ID74 p.8: "If tube thoracostomy placement is delayed, providers should be prepared to repeat needle decompression as needed."

**2. No improvement after two needle decompressions most likely means another diagnosis.**
- ID74 p.8: "Failure to improve after two needle decompressions most likely indicates an alternative diagnosis to pneumothorax (e.g., hemothorax, pulmonary contusion, and diaphragm injury)."

### DON'T

**1. Do not use short (5 cm) venous-access catheters: they rarely reach the chest cavity.**
- ID74 p.8: "shorter (5cm) catheters used for venous access should be avoided as these will rarely penetrate the thoracic cavity and thus be ineffective."

**2. Do not wait for imaging: absent or markedly decreased breath sounds after chest trauma indicate intervention without further testing.**
- ID74 p.5: "Absent or markedly decreased breath sounds in a patient with known thoracic trauma indicate the need for intervention without additional diagnostic testing."

### THEN (only with shock physiology)

**1. After decompression, then reassess for hemorrhage — DCR (damage-control resuscitation) if shock persists: control bleeding, blood products, TXA within 3 hours.**
- ID74 p.5: "While a patient with thoracic trauma and a pneumothorax may present with multiple injuries and an alternate explanation for hypotension (such as cardiac tamponade, intraabdominal bleeding, or hemothorax), immediate needle or tube thoracostomy is the necessary first step in this scenario."

The THEN line's DCR steps are the signed DCR card's (owner ruling 1, 2026-09-24); ID74 p.5 is cited for the order: decompression first.

### TLDR

**1. Suspected tension pneumothorax: needle decompress, 14 gauge 8cm catheter, 4th/5th ICS anterior axillary line, then tube thoracostomy.**
- ID74 p.8: "Needle decompression should be performed with a large bore (14 gauge or larger) 3.25in/8cm catheter in the 4th or 5th intercostal space, anterior axillary line."
- ID74 p.8: "Needle decompression alone is insufficient treatment for a pneumothorax and certainly ineffective for hemothorax and should in most cases be followed by placement of a tube thoracostomy as soon as feasible and safe."

### SOURCE line

"JTS CPG ID74, Wartime Thoracic Injury (26 Dec 2018), p.5 (recognition), p.8 (needle decompression)"

## Signing

Sign as drafted, or rule otherwise on any line. On signature: `signoff: true`, `reviewed_by`, `review_date` in the file; a test pins the signed text; the replay runs.
