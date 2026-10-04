// V-Assure "V" logomark in SVG
export function VAssureLogo({size= 52}: {size?: number}) {
  return (
    <svg width={size} height={size} viewBox="0 0 52 52" fill="none" xmlns="http://www.w3.org/2000/svg">
      {/* Orange circle background */}
      <circle cx="26" cy="26" r="26" fill="#F5A623" />
      {/* White V shape */}
      <path
        d="M13 14 L26 38 L39 14"
        stroke="white"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
      {/* Inner grey triangle */}
      <path
        d="M19 14 L26 28 L33 14"
        stroke="rgba(255,255,255,0.35)"
        strokeWidth="3"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}