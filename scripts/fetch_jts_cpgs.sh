#!/usr/bin/env bash
# =============================================================================
# EdgeCDSS knowledge-base recovery: re-download JTS CPG PDFs from jts.health.mil
# =============================================================================
# The data/ folder is gitignored (too large for the repo). This script rebuilds
# it from the public source. Run from the repo root:
#
#   bash scripts/fetch_jts_cpgs.sh
#
# Then rebuild the vector DB:
#
#   pip install -r requirements-server.txt
#   python server/ingest_jts.py
#
# NOTE: jts.health.mil updates CPGs over time. A fresh download may differ from
# the knowledge base a given release was tested against. For the exact certified
# KB, use the chromadb snapshot from the GitHub Releases page instead.
# URL list captured: 2026-08-09
# =============================================================================
set -u
OUT="data/jts"
mkdir -p "$OUT"
OK=0; FAIL=0; SKIP=0; FAILED_URLS=()

URLS=(
"https://jts.health.mil/assets/docs/cpgs/Spider_and_Scorpion_Envenomation_21_Jul_2026_ID84_v1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Orthopaedic_Trauma_Extremity_Fractures_ID56_22_Jun_2026.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Healthcare_Provider_Responsibilities_CPG_C1_22_Jun_2026.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Hypothermia_CPG_C10_22_June_2026.pdf"
"https://jts.health.mil/assets/docs/cpgs/Dried_Plasma_CPG_09_Jun_2026_ID103.pdf"
"https://jts.health.mil/assets/docs/cpgs/Extremity_Compartment_Syndrome_and_Fasciotomy_ID17_21_May_2026.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Medical_Records_Documentation_CPG_c22_01_APR_2026.pdf"
"https://jts.health.mil/assets/docs/cpgs/Snakebite_Envenomation_CPG_ID81_26_Apr_2026_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/CBRN_Injury_Part1_Initial_Response_08_Apr_2026_ID69_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Pelvic_Fracture_Care_17_Feb_2026_ID34v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Airway_Management_in_Trauma_28_Jan_2026_ID39.pdf"
"https://jts.health.mil/assets/docs/cpgs/REBOA_for_Hemorrhagic_Shock_4.3.2026_ID38_v1.4.pdf"
"https://jts.health.mil/assets/docs/cpgs/Blunt_Abdominal_Trauma_Splenectomy_Vaccination_13_May_2020_ID09.pdf"
"https://jts.health.mil/assets/docs/cpgs/Altitude_Emergencies_Prehospital_Environment_05_Mar_2024_ID95_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Infection_Prevention_in_Combat-related_Injuries_27_Jan_2021_ID24.pdf"
"https://jts.health.mil/assets/docs/cpgs/Invasive_Fungal_Infection_in_War_Wounds_17_Jul_2023_ID28_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Sepsis_Management_PFC_28_Oct_2020_ID83.pdf"
"https://jts.health.mil/assets/docs/cpgs/Ventilator_Associated_Pneumonia_(VAP)_07_May_2020_ID45.pdf"
"https://jts.health.mil/assets/docs/cpgs/Aural_Blast_Injury_Acoustic_Trauma_and_Hearing_Loss_14_Aug_2025_ID05_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Prehospital_Blood_Transfusion_30_Oct_2020_ID82.pdf"
"https://jts.health.mil/assets/docs/cpgs/Damage_Control_Resuscitation_12_Jul_2019_ID18.pdf"
"https://jts.health.mil/assets/docs/cpgs/Damage_Control_Resuscitation_PFC_01_Oct_2018_ID73.pdf"
"https://jts.health.mil/assets/docs/cpgs/Frozen_Deglycerolized_Red-Blood_Cells_05_Aug_2024_ID26_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Type_A_Specific_WB_Transfusion_30_May_2025_ID96_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Whole_Blood_Transfusion_15_May_2018_ID21.pdf"
"https://jts.health.mil/assets/docs/cpgs/Burn_Care_CPG_10_June_2025_ID12_v1.3.pdf"
"https://jts.health.mil/assets/docs/cpgs/Burn_Management_PFC_13_Jan_2017_ID57.pdf"
"https://jts.health.mil/assets/docs/cpgs/Acute_Coronary_Syndrome_14_May_2021_ID86.pdf"
"https://jts.health.mil/assets/docs/cpgs/CBRN_Injury_Response_Part_2_Medical_Management_25_Mar_2022_ID69.pdf"
"https://jts.health.mil/assets/docs/cpgs/CBRN_3_20_Aug_2024_ID93_v1.3.pdf"
"https://jts.health.mil/assets/docs/cpgs/CBRN_Part_4_General_Approach_to_Biological_Casualties_27_Feb_2025_ID101.pdf"
"https://jts.health.mil/assets/docs/cpgs/Radiofrequency_EMF_Overexposure_CPG_12_Jul_2024_ID98_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Emergent_Resuscitative_Thoracotomy_ERT_18_Jul_2018_ID20.pdf"
"https://jts.health.mil/assets/docs/cpgs/Wartime_Thoracic_Injury_26_Dec_2018_ID74.pdf"
"https://jts.health.mil/assets/docs/cpgs/Frostbite_and_Immersion_Foot_Care_26_Jan_2017_ID_59.pdf"
"https://jts.health.mil/assets/docs/cpgs/Hypothermia_Prevention_Treatment_07_Jun_2023_ID23.pdf"
"https://jts.health.mil/assets/docs/cpgs/JTS_CPG_Development_Process_04_Oct_2024_ID54.pdf"
"https://jts.health.mil/assets/docs/cpgs/JTS_CPG_Author_Guidance_28_Aug_2024.pdf"
"https://jts.health.mil/assets/docs/cpgs/Documentation_Prolonged_Field_Care_13_Nov_2018_ID72_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Documentation_Requirements_for_Combat_Casualty_Care_18_Sep_2020_ID11.pdf"
"https://jts.health.mil/assets/docs/cpgs/Drowning_Management_17_Mar_2025_ID64_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Genitourinary_Injury_Trauma_Management_29_Mar_2024_ID42_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Hyperkalemia_and_Dialysis_in_Deployed_Setting_25_Apr_2022_ID52.pdf"
"https://jts.health.mil/assets/docs/cpgs/War_Wounds_Debridement_and_Irrigation_27_Sep_2021_ID31.pdf"
"https://jts.health.mil/assets/docs/cpgs/Wound_Management_PFC_24_Jul_2017_ID62.pdf"
"https://jts.health.mil/assets/docs/cpgs/Catastrophic_Non-Survivable_Brain_Injury_27_Jan_2017_ID13.pdf"
"https://jts.health.mil/assets/docs/cpgs/Emergency_Cranial_Procedures_by_Non-neurosurgeons_10_June_2025_ID68_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/TBI_Neurosurgery_Deployed%20Environment_15_Sep_2023_ID30_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Traumatic_Brain_Injury_PFC_06_Dec_2017_ID63.pdf"
"https://jts.health.mil/assets/docs/cpgs/Use_of_TBI_Biomarkers_after_Potentially_Concussive_Event_14_Apr_2025_ID90_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Nursing_Interventions_PCC_08_July_2025_ID70_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Nutrition_Using_Enteral_and_Parenteral_Methods_04_Aug_2016_ID33.pdf"
"https://jts.health.mil/assets/docs/cpgs/Eye_Trauma_Initial_Care_01_Jun_2021_ID03.pdf"
"https://jts.health.mil/assets/docs/cpgs/Ocular_Evaluation_Disposition_After_Laser_Exposure_14_Feb_2020_ID79.pdf"
"https://jts.health.mil/assets/docs/cpgs/Ocular_Injuries_Vision-Threatening_Conditions_PFC_01_Dec_2017_ID66.pdf"
"https://jts.health.mil/assets/docs/cpgs/Amputation_Evaluation_and_Treatment_10_Oct_2024_ID07_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/High_Bilateral_Amputations_Dismounted_Complex_Blast_Injury_05_Aug_2024_ID22_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Cervical_Thoracolumbar_Spine_Injury_19_Jun_2020_ID15.pdf"
"https://jts.health.mil/assets/docs/cpgs/Crush_Syndrome_PFC_28_Dec_2016_ID58.pdf"
"https://jts.health.mil/assets/docs/cpgs/Analgesia_and_Sedation_Management_during_PFC_11_May_2017_ID61.pdf"
"https://jts.health.mil/assets/docs/cpgs/Anesthesia_for_Trauma_Patients_05_Apr_2021_ID40.pdf"
"https://jts.health.mil/assets/docs/cpgs/Pain_Anxiety_Delirium_26_Apr_2021_ID29_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Prolonged_Casualty_Care_Guidelines_21_Dec_2021_ID91.pdf"
"https://jts.health.mil/assets/docs/cpgs/Radiology_Imaging_Trauma_Patients_in_Deployed_Setting_13_Mar_2017_ID01.pdf"
"https://jts.health.mil/assets/docs/cpgs/Inhalation_Injury_Toxic_and_Industrial_Chemical_Exposure_26_Jul_2016_ID25.pdf"
"https://jts.health.mil/assets/docs/cpgs/Mechnical_Ventilation_Basics_09_Apr_2025_ID92_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Acute_Respiratory_Failure_23_Jan_2017_ID06_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Emergency_General_Surgery_in_Deployed_Locations_01_Aug_2018_ID71.pdf"
"https://jts.health.mil/assets/docs/cpgs/Austere_Resuscitative_Surgical_Care_30_Oct_2019_ID76.pdf"
"https://jts.health.mil/assets/docs/cpgs/Vascular_Injury_09_Apr_2025_ID46_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Telemedicine_Deployed_Setting_19_Sep_2023_ID94_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/En_Route_Care_Patient_Packaging_21_Aug_2024_ID97_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Interfacility_Transport_CoERCCC_OPG.pdf"
"https://jts.health.mil/assets/docs/cpgs/Unexploded_Ordnance_(UXO)_Management_14_Mar_2017_ID41.pdf"
"https://jts.health.mil/assets/docs/cpgs/Prevention_of_Venous_Thromboembolism_29_Mar_2024_ID36v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/Transfusion_in_Military_Working_Dog_10_Dec_2019_ID77.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Airway_Management_CPG_c3_18_Dec_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/Arachnid_Snake_Envenomation_MWD_CPG_c11_29_Mar_2025_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Blast_Burn_Crush_Injuries_CPG_c12_30_Dec_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_C-PTS_C-PTSD_CPG_c18_14_Aug_2025_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_CPR_CPG_c5_14_Aug_2025_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Euthanasia_MWD_CPG_c21_03_Apr_2025_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Heat_Injury_MWD_CPG_c9_29_Mar_2025_v1.1.pdf"
"https://jts.health.mil/assets/docs/cpgs/Normal_Clinical_Parameters_MWD_c2_05_May_2025_v1.2.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Ocular_Injuries_CPG_c15_30_Dec_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/K9_Wound_Management_CPG_c14_18_Dec_2025.pdf"
"https://jts.health.mil/assets/docs/ADVISOR_Teleconsultation_Flyer.pdf"
"https://jts.health.mil/assets/docs/cpgs/Mental_Health_Mar_2026.pdf"
"https://jts.health.mil/assets/docs/Management_of_COVID-19_in_Austere_Operational_Environments.pdf"
"https://jts.health.mil/assets/docs/cpgs/Mechanical_Ventilation_CCATT_10_MAR_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/NPWT_CCATT_26_Feb_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/US_Army_Aeromedical_Evacuation_Standard_Medical_Operating_Guidelines_26NOV2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/Stroke_Cerebrovascular_Emergencies_Deployed_Setting_03_July_2024.pdf"
"https://jts.health.mil/assets/docs/cpgs/UPAC_Ventilation_Guide.pdf"
"https://jts.health.mil/assets/docs/cpgs/i-STAT_Portable_CCATT_Final_26_FEB_2025.pdf"
"https://jts.health.mil/assets/docs/cpgs/Progressive_Return_to_Activity_Primary_Care_for_Acute_Concussion_Management_January_2024.pdf"
"https://jts.health.mil/assets/docs/cpgs/MWD_CPG_12_Dec_2018_ID16_v1.8.pdf"
)

echo "Fetching ${#URLS[@]} JTS CPG PDFs into $OUT/ ..."
for url in "${URLS[@]}"; do
  fname="$(basename "$url" | sed 's/%20/_/g')"
  dest="$OUT/$fname"
  if [ -s "$dest" ]; then SKIP=$((SKIP+1)); continue; fi
  if wget -q --timeout=60 --tries=3 --user-agent="Mozilla/5.0 (EdgeCDSS KB recovery; open-source research)" -O "$dest" "$url"; then
    # sanity: real PDF, not an error page
    if head -c4 "$dest" | grep -q "%PDF"; then
      OK=$((OK+1)); echo "  ok  $fname"
    else
      FAIL=$((FAIL+1)); FAILED_URLS+=("$url"); rm -f "$dest"; echo "  BAD (not a PDF) $fname"
    fi
  else
    FAIL=$((FAIL+1)); FAILED_URLS+=("$url"); rm -f "$dest"; echo "  FAIL $fname"
  fi
  sleep 1   # be polite to the JTS server
done

echo
echo "Done: $OK downloaded, $SKIP already present, $FAIL failed."
if [ ${#FAILED_URLS[@]} -gt 0 ]; then
  echo "Failed URLs (JTS may have updated filenames — check jts.health.mil/index.cfm/PI_CPGs/cpgs):"
  printf '  %s\n' "${FAILED_URLS[@]}"
fi
echo
echo "Next: pip install -r requirements-server.txt && python server/ingest_jts.py"
