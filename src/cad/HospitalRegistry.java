package cad;

import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

/** In-memory hospital capacity registry; allocation is O(h) due to alternate-facility scanning. */
public final class HospitalRegistry {
    public static final class Allocation {
        private final String hospitalName;
        private final boolean diverted;
        private Allocation(String hospitalName, boolean diverted) {
            this.hospitalName = hospitalName; this.diverted = diverted;
        }
        public String getHospitalName() { return hospitalName; }
        public boolean isDiverted() { return diverted; }
        public boolean isAllocated() { return hospitalName != null; }
    }
    private static final class Hospital {
        private final int initialIcuBeds;
        private int icuBeds;
        private final Map<String, Integer> initialSpecialtyBays = new LinkedHashMap<>();
        private final Map<String, Integer> specialtyBays = new LinkedHashMap<>();
        private final boolean initiallyActive;
        private boolean active;
        private Hospital(int icuBeds, boolean active) {
            this.initialIcuBeds = icuBeds;
            this.icuBeds = icuBeds;
            this.initiallyActive = active;
            this.active = active;
        }
    }

    private final Map<String, Hospital> hospitals = new LinkedHashMap<>();

    public void registerHospital(String name, int icuBeds, Map<String, Integer> specialtyBays) {
        registerHospital(name, icuBeds, specialtyBays, true);
    }

    public void registerHospital(String name, int icuBeds, Map<String, Integer> specialtyBays, boolean active) {
        if (name == null || name.isBlank()) throw new IllegalArgumentException("Hospital name cannot be blank.");
        if (icuBeds < 0) throw new IllegalArgumentException("ICU bed capacity cannot be negative.");
        if (hospitals.containsKey(name.trim())) throw new IllegalArgumentException("Hospital already registered: " + name);
        Hospital hospital = new Hospital(icuBeds, active);
        if (specialtyBays != null) for (Map.Entry<String, Integer> bay : specialtyBays.entrySet()) {
            if (bay.getKey() == null || bay.getKey().isBlank() || bay.getValue() == null || bay.getValue() < 0)
                throw new IllegalArgumentException("Specialty bay names and capacities must be valid.");
            String specialty = normalizeSpecialty(bay.getKey());
            hospital.specialtyBays.put(specialty, bay.getValue());
            hospital.initialSpecialtyBays.put(specialty, bay.getValue());
        }
        hospitals.put(name.trim(), hospital);
    }

    public void setActive(String hospitalName, boolean active) { requireHospital(hospitalName).active = active; }

    public boolean isActive(String hospitalName) { return requireHospital(hospitalName).active; }

    public boolean contains(String hospitalName) { return hospitals.containsKey(hospitalName); }

    public void restoreDefaults() {
        for (Hospital hospital : hospitals.values()) {
            hospital.icuBeds = hospital.initialIcuBeds;
            hospital.specialtyBays.clear();
            hospital.specialtyBays.putAll(hospital.initialSpecialtyBays);
            hospital.active = hospital.initiallyActive;
        }
    }

    public List<Map<String, Object>> snapshot() {
        java.util.ArrayList<Map<String, Object>> result = new java.util.ArrayList<>();
        for (Map.Entry<String, Hospital> entry : hospitals.entrySet()) {
            Hospital hospital = entry.getValue();
            Map<String, Object> item = new LinkedHashMap<>();
            item.put("name", entry.getKey());
            item.put("beds", hospital.icuBeds);
            item.put("active", hospital.active);
            item.put("specialtyBays", Map.copyOf(hospital.specialtyBays));
            result.add(Map.copyOf(item));
        }
        return List.copyOf(result);
    }

    /** Reserves ICU capacity and a requested specialized bay; diverts to the first suitable facility. */
    public Allocation allocateBedOrDivert(String primaryHospital, String specialty) {
        if (primaryHospital == null || primaryHospital.isBlank()) throw new IllegalArgumentException("Primary hospital cannot be blank.");
        String normalized = normalizeSpecialty(specialty == null || specialty.isBlank() ? "GENERAL" : specialty);
        Hospital primary = hospitals.get(primaryHospital.trim());
        if (primary == null) throw new IllegalArgumentException("Unknown primary hospital: " + primaryHospital);
        if (reserve(primary, normalized)) return new Allocation(primaryHospital.trim(), false);
        for (Map.Entry<String, Hospital> candidate : hospitals.entrySet()) {
            if (!candidate.getKey().equals(primaryHospital.trim()) && reserve(candidate.getValue(), normalized))
                return new Allocation(candidate.getKey(), true);
        }
        return new Allocation(null, true);
    }

    public int getAvailableIcuBeds(String hospitalName) {
        return requireHospital(hospitalName).icuBeds;
    }

    private static boolean reserve(Hospital hospital, String specialty) {
        if (!hospital.active || hospital.icuBeds <= 0) return false;
        Integer bays = "GENERAL".equals(specialty) ? null : hospital.specialtyBays.get(specialty);
        if (!"GENERAL".equals(specialty) && (bays == null || bays <= 0)) return false;
        hospital.icuBeds--;
        if (bays != null) hospital.specialtyBays.put(specialty, bays - 1);
        return true;
    }

    private static String normalizeSpecialty(String specialty) {
        if (specialty == null || specialty.isBlank()) return "GENERAL";
        return specialty.trim().toUpperCase(java.util.Locale.ROOT);
    }

    private Hospital requireHospital(String hospitalName) {
        Hospital hospital = hospitals.get(hospitalName);
        if (hospital == null) throw new IllegalArgumentException("Unknown hospital: " + hospitalName);
        return hospital;
    }
}