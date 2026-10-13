// Display-only cleanup. Identifiers, form values and API payloads stay original.
export function cleanDisplayText(value) {
  if (typeof value !== 'string') return value ?? '';
  return value
    .replace(/#+[ \t]*(?=\d)/g, (match, offset, text) =>
      offset > 0 && /\S/.test(text[offset - 1]) ? ' ' : '')
    .replace(/â€¢|•/g, ' ')
    .replace(/[ \t]{2,}/g, ' ')
    .trim();
}
