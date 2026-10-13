import { useState } from 'react';
import { ChevronDown, Info } from 'lucide-react';
import type { AssessmentContext, PolicyAddOn, PolicyCategory } from '../types/assessment';

interface AssessmentContextFormProps {
  value: AssessmentContext;
  onChange: (value: AssessmentContext) => void;
}

const addOns: Array<{ value: PolicyAddOn; label: string }> = [
  { value: 'zero_depreciation', label: 'Zero depreciation' },
  { value: 'engine_protection', label: 'Engine protection' },
  { value: 'consumables_cover', label: 'Consumables cover' },
  { value: 'return_to_invoice', label: 'Return to invoice' },
  { value: 'roadside_assistance', label: 'Roadside assistance' },
];

export function AssessmentContextForm({ value, onChange }: AssessmentContextFormProps) {
  const [expanded, setExpanded] = useState(false);
  const set = <K extends keyof AssessmentContext>(key: K, next: AssessmentContext[K]) => onChange({ ...value, [key]: next });
  const toggleAddOn = (addOn: PolicyAddOn) => {
    const selected = value.policy_add_ons.includes(addOn);
    set('policy_add_ons', selected ? value.policy_add_ons.filter((item) => item !== addOn) : [...value.policy_add_ons, addOn]);
  };

  return (
    <section className="mt-6 overflow-hidden rounded-[12px] border border-line bg-canvas/35" aria-labelledby="context-heading">
      <button type="button" className="flex w-full items-center justify-between gap-4 px-4 py-3.5 text-left" onClick={() => setExpanded((current) => !current)} aria-expanded={expanded}>
        <span><span className="eyebrow">Optional context</span><span id="context-heading" className="mt-1 block text-sm font-semibold text-ink">Improve INR scenarios and policy guidance</span></span>
        <ChevronDown size={17} className={`shrink-0 text-muted transition-transform ${expanded ? 'rotate-180' : ''}`} aria-hidden="true" />
      </button>
      {expanded && (
        <div className="border-t border-line px-4 py-4 motion-enter">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            <Field label="City or region" value={value.city_or_region || ''} onChange={(next) => set('city_or_region', next || null)} placeholder="e.g. Pune" />
            <Field label="Vehicle make" value={value.vehicle_make || ''} onChange={(next) => set('vehicle_make', next || null)} placeholder="e.g. Tata" />
            <Field label="Vehicle model" value={value.vehicle_model || ''} onChange={(next) => set('vehicle_model', next || null)} placeholder="e.g. Nexon" />
            <Field label="Vehicle year" value={value.vehicle_year?.toString() || ''} onChange={(next) => set('vehicle_year', next ? Number(next) : null)} placeholder="e.g. 2022" inputMode="numeric" />
            <Field label="Variant (optional)" value={value.vehicle_variant || ''} onChange={(next) => set('vehicle_variant', next || null)} placeholder="e.g. XZ+" />
            <Field label="Fuel / powertrain" value={value.fuel_or_powertrain || ''} onChange={(next) => set('fuel_or_powertrain', next || null)} placeholder="e.g. Petrol" />
            <div className="sm:col-span-2 lg:col-span-3"><Field label="Incident cause (if known)" value={value.incident_cause || ''} onChange={(next) => set('incident_cause', next || null)} placeholder="e.g. Parking impact, unknown" /></div>
          </div>

          <div className="mt-6 border-t border-line pt-5">
            <div className="flex items-start gap-2"><Info size={15} className="mt-0.5 shrink-0 text-accent" aria-hidden="true" /><p className="text-xs leading-5 text-muted">Insurance details are optional. Do not enter policy numbers, payment details, or other sensitive identifiers.</p></div>
            <div className="mt-4 grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
              <SelectField label="Policy category" value={value.policy_category} onChange={(next) => set('policy_category', next as PolicyCategory)} options={[['unknown', 'I am not sure'], ['third_party_liability', 'Third-party liability'], ['comprehensive_package', 'Comprehensive / package'], ['standalone_own_damage', 'Standalone own-damage']]} />
              <Field label="Insurer (if known)" value={value.insurer || ''} onChange={(next) => set('insurer', next || null)} placeholder="Optional" />
              <Field label="Deductible / excess (₹)" value={value.deductible_inr?.toString() || ''} onChange={(next) => set('deductible_inr', next ? Number(next) : null)} placeholder="Optional" inputMode="numeric" />
              <Field label="Policy start" type="date" value={value.policy_start_date || ''} onChange={(next) => set('policy_start_date', next || null)} />
              <Field label="Policy end" type="date" value={value.policy_end_date || ''} onChange={(next) => set('policy_end_date', next || null)} />
            </div>
            <fieldset className="mt-5"><legend className="text-xs font-semibold text-ink">Known add-ons</legend><div className="mt-3 grid gap-2 sm:grid-cols-2 lg:grid-cols-3">{addOns.map((addOn) => <label key={addOn.value} className="flex items-center gap-2 text-xs text-muted"><input type="checkbox" className="h-4 w-4 rounded border-line accent-accent" checked={value.policy_add_ons.includes(addOn.value)} onChange={() => toggleAddOn(addOn.value)} />{addOn.label}</label>)}</div></fieldset>
          </div>
        </div>
      )}
    </section>
  );
}

function Field({ label, value, onChange, placeholder, inputMode, type = 'text' }: { label: string; value: string; onChange: (value: string) => void; placeholder?: string; inputMode?: 'numeric'; type?: 'text' | 'date' }) {
  return <label className="block"><span className="text-xs font-semibold text-ink">{label}</span><input type={type} className="mt-1.5 min-h-10 w-full rounded-[8px] border border-line bg-panel px-3 text-sm text-ink placeholder:text-slate-400 focus:border-accent focus:outline-none" value={value} placeholder={placeholder} onChange={(event) => onChange(event.target.value)} inputMode={inputMode} /></label>;
}

function SelectField({ label, value, onChange, options }: { label: string; value: string; onChange: (value: string) => void; options: Array<[string, string]> }) {
  return <label className="block"><span className="text-xs font-semibold text-ink">{label}</span><select className="mt-1.5 min-h-10 w-full rounded-[8px] border border-line bg-panel px-3 text-sm text-ink focus:border-accent focus:outline-none" value={value} onChange={(event) => onChange(event.target.value)}>{options.map(([optionValue, optionLabel]) => <option key={optionValue} value={optionValue}>{optionLabel}</option>)}</select></label>;
}
