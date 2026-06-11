/**
 * OTH listing URL helpers.
 *
 * URL pattern discovered from raw OTH JSON fixtures
 * (services/oth-scraper/tests/fixtures/oth/):
 *
 * The OTH API returns a `links` array on every property/listing object.
 * The entry with `rel === "othWebUrl"` is the canonical frontend URL.
 *
 * Pattern breakdown:
 *   forsale:      https://www.onthehouse.com.au/property-for-sale/{state}/{suburb}-{postcode}/{address-slug}-{othListingId}
 *   forrent:      https://www.onthehouse.com.au/property-for-rent/{state}/{suburb}-{postcode}/{address-slug}-{othListingId}
 *   recentlysold: https://www.onthehouse.com.au/property/{state}/{suburb}-{postcode}/{address-slug}-{othPropertyId}
 *
 * Address slug: formattedAddress.toLowerCase(), commas removed, "/" → "-", spaces → "-"
 *   e.g. "1/267 GIVEN TCE, PADDINGTON, QLD 4064" → "1-267-given-tce-paddington-qld-4064"
 *
 * For the property table we only have oth_property_id (not oth_listing_id), so
 * forsale/forrent rows also use the /property/ path (property overview page).
 * For individual listing pages we have oth_listing_id and use the category-specific path.
 */

const OTH_BASE = 'https://www.onthehouse.com.au'

/** Convert a formatted address into an OTH path slug. */
function addressToSlug(formattedAddress) {
  return formattedAddress
    .toLowerCase()
    .replace(/,/g, '')    // remove commas
    .replace(/\//g, '-')  // unit separator "1/267" → "1-267"
    .trim()
    .replace(/\s+/g, '-') // spaces → hyphens
}

/**
 * Extract the state code (lowercase) from a formatted address.
 * Formatted address ends with ", {STATE} {POSTCODE}", e.g. ", QLD 4064".
 * Returns null if the address doesn't match expected format.
 *
 * @param {string} formattedAddress - e.g. "115 ROCKBOURNE TCE, PADDINGTON, QLD 4064"
 * @returns {string|null} - e.g. "qld"
 */
function stateFromAddress(formattedAddress) {
  const parts = formattedAddress.split(',')
  const last = parts[parts.length - 1]?.trim() // "QLD 4064"
  const statePostcode = last?.split(/\s+/)
  return statePostcode?.[0]?.toLowerCase() ?? null
}

/**
 * Extract the suburb slug (lowercase) from a formatted address.
 * Second-to-last comma-separated component.
 *
 * @param {string} formattedAddress - e.g. "115 ROCKBOURNE TCE, PADDINGTON, QLD 4064"
 * @returns {string|null} - e.g. "paddington"
 */
function suburbFromAddress(formattedAddress) {
  const parts = formattedAddress.split(',')
  return parts[parts.length - 2]?.trim().toLowerCase() ?? null
}

/**
 * Build an OTH listing/property URL from the data available in
 * PropertyWithRollup (suburb page table).
 *
 * Uses oth_property_id + the /property/ path for all categories since the
 * table rollup doesn't include oth_listing_id.
 *
 * @param {Object} params
 * @param {string|null} params.othPropertyId  - from property.oth_property_id
 * @param {string}      params.formattedAddress
 * @param {string}      params.postcode
 * @returns {string|null}
 */
export function othPropertyUrl({ othPropertyId, formattedAddress, postcode }) {
  if (!othPropertyId || !formattedAddress || !postcode) return null

  const state = stateFromAddress(formattedAddress)
  const suburb = suburbFromAddress(formattedAddress)
  if (!state || !suburb) return null

  const slug = addressToSlug(formattedAddress)
  return `${OTH_BASE}/property/${state}/${suburb}-${postcode}/${slug}-${othPropertyId}`
}

/**
 * Build an OTH listing URL for a specific listing campaign.
 * Used on the PropertyDetailPage per-listing card and ListingDetailPage header.
 *
 * @param {Object} params
 * @param {string|null} params.othListingId   - from listing.oth_listing_id
 * @param {string|null} params.othPropertyId  - from property.oth_property_id (fallback for recentlysold)
 * @param {string}      params.category       - "forsale" | "forrent" | "recentlysold"
 * @param {string}      params.formattedAddress
 * @param {string}      params.postcode
 * @returns {string|null}
 */
export function othListingUrl({ othListingId, othPropertyId, category, formattedAddress, postcode }) {
  if (!formattedAddress || !postcode) return null

  const state = stateFromAddress(formattedAddress)
  const suburb = suburbFromAddress(formattedAddress)
  if (!state || !suburb) return null

  const slug = addressToSlug(formattedAddress)

  if (category === 'recentlysold') {
    if (!othPropertyId) return null
    return `${OTH_BASE}/property/${state}/${suburb}-${postcode}/${slug}-${othPropertyId}`
  }

  if (!othListingId) return null
  const path = category === 'forrent' ? 'property-for-rent' : 'property-for-sale'
  return `${OTH_BASE}/${path}/${state}/${suburb}-${postcode}/${slug}-${othListingId}`
}

/**
 * Extract the OTH web URL from a raw_payload object (listing_snapshot.raw_payload).
 * This is the canonical URL from the OTH API itself, stored verbatim.
 *
 * @param {Object|null} rawPayload - listing_snapshot.raw_payload
 * @returns {string|null}
 */
export function othUrlFromRawPayload(rawPayload) {
  if (!rawPayload?.links) return null
  const entry = rawPayload.links.find((l) => l.rel === 'othWebUrl')
  return entry?.href ?? null
}

// ---------------------------------------------------------------------------
// Sanity assertions (run at module evaluation time in dev — harmless in prod)
// ---------------------------------------------------------------------------

console.assert(
  othPropertyUrl({
    othPropertyId: '3177937',
    formattedAddress: '64 GUTHRIE ST, PADDINGTON, QLD 4064',
    postcode: '4064',
  }) === 'https://www.onthehouse.com.au/property/qld/paddington-4064/64-guthrie-st-paddington-qld-4064-3177937',
  'othPropertyUrl recentlysold'
)

console.assert(
  othListingUrl({
    othListingId: '18548014',
    othPropertyId: '3183143',
    category: 'forsale',
    formattedAddress: '115 ROCKBOURNE TCE, PADDINGTON, QLD 4064',
    postcode: '4064',
  }) === 'https://www.onthehouse.com.au/property-for-sale/qld/paddington-4064/115-rockbourne-tce-paddington-qld-4064-18548014',
  'othListingUrl forsale'
)

console.assert(
  othListingUrl({
    othListingId: '18534929',
    othPropertyId: '3175209',
    category: 'forrent',
    formattedAddress: '43 BOWLER ST, PADDINGTON, QLD 4064',
    postcode: '4064',
  }) === 'https://www.onthehouse.com.au/property-for-rent/qld/paddington-4064/43-bowler-st-paddington-qld-4064-18534929',
  'othListingUrl forrent'
)

console.assert(
  othListingUrl({
    othListingId: '99999',
    othPropertyId: '3711495',
    category: 'recentlysold',
    formattedAddress: '1/267 GIVEN TCE, PADDINGTON, QLD 4064',
    postcode: '4064',
  }) === 'https://www.onthehouse.com.au/property/qld/paddington-4064/1-267-given-tce-paddington-qld-4064-3711495',
  'othListingUrl recentlysold unit number'
)

console.assert(othPropertyUrl({ othPropertyId: null, formattedAddress: '64 GUTHRIE ST, PADDINGTON, QLD 4064', postcode: '4064' }) === null, 'othPropertyUrl null id')
console.assert(othListingUrl({ othListingId: null, othPropertyId: null, category: 'forsale', formattedAddress: 'X, Y, QLD 4000', postcode: '4000' }) === null, 'othListingUrl null ids')
