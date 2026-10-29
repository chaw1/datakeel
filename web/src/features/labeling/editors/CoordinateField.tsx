export function CoordinateField({
  label,
  value,
  max,
  onChange,
  readOnly,
}: {
  label: string;
  value: number;
  max: number;
  onChange: (value: number) => void;
  readOnly?: boolean;
}) {
  return (
    <label>
      {label}
      <input
        type="number"
        min={0}
        max={max}
        step="any"
        value={value}
        readOnly={readOnly}
        onChange={(event) => {
          const number = event.target.valueAsNumber;
          if (Number.isFinite(number) && number >= 0 && number <= max)
            onChange(number);
        }}
      />
    </label>
  );
}
