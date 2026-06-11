import React from 'react';

const outputJsonModules = import.meta.glob('../../../../output/*.json', { eager: true });

const currencyFormatter = new Intl.NumberFormat('en-AU', {
  style: 'currency',
  currency: 'AUD',
  maximumFractionDigits: 0,
});

const PRICE_KEYS = [
  'sale_price',
  'salePrice',
  'price',
  'soldPrice',
  'lastSalePrice',
];

const toNumber = (value) => {
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }

  if (typeof value === 'string') {
    const cleaned = value.replace(/[^\d.]/g, '');
    if (!cleaned) {
      return null;
    }
    const parsed = Number.parseFloat(cleaned);
    return Number.isFinite(parsed) ? parsed : null;
  }

  return null;
};

const normalizeSuburb = (suburb) => {
  if (typeof suburb !== 'string') {
    return null;
  }

  const cleaned = suburb.trim().replace(/\s+/g, ' ');
  return cleaned ? cleaned.toUpperCase() : null;
};

const extractSuburbFromAddress = (address) => {
  if (typeof address !== 'string' || !address.trim()) {
    return null;
  }

  const parts = address
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);

  if (parts.length < 2) {
    return null;
  }

  const stateIndex = parts.findIndex((part) => /\bQLD\b/i.test(part));
  if (stateIndex > 0) {
    return normalizeSuburb(parts[stateIndex - 1]);
  }

  return normalizeSuburb(parts[1]);
};

const getSuburb = (item, fallbackSuburb) => {
  const directSuburb =
    item.suburb ||
    item.suburbName ||
    item.locality ||
    item.city ||
    item.addressSuburb;

  const normalizedDirect = normalizeSuburb(directSuburb);
  if (normalizedDirect) {
    return normalizedDirect;
  }

  const schoolNameSuburb = extractSuburbFromAddress(item.schoolName);
  if (schoolNameSuburb) {
    return schoolNameSuburb;
  }

  const addressSuburb = extractSuburbFromAddress(item.address);
  if (addressSuburb) {
    return addressSuburb;
  }

  return normalizeSuburb(fallbackSuburb);
};

const getPrice = (item) => {
  for (const key of PRICE_KEYS) {
    const value = toNumber(item[key]);
    if (value) {
      return value;
    }
  }

  if (item.lastSale && typeof item.lastSale === 'object') {
    const nested = toNumber(item.lastSale.salePrice);
    if (nested) {
      return nested;
    }
  }

  return null;
};

const toItems = (data) => {
  if (Array.isArray(data)) {
    return { items: data, fallbackSuburb: null };
  }

  if (!data || typeof data !== 'object') {
    return { items: [], fallbackSuburb: null };
  }

  const arrayCandidate =
    data.properties ||
    data.items ||
    data.listings ||
    data.results ||
    data.data;

  if (Array.isArray(arrayCandidate)) {
    return { items: arrayCandidate, fallbackSuburb: data.suburb || data.suburbName || null };
  }

  return { items: [data], fallbackSuburb: data.suburb || data.suburbName || null };
};

const formatSuburbLabel = (suburb) =>
  suburb
    .toLowerCase()
    .split(' ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');

function PropertyPriceCards() {
  const suburbSummaries = React.useMemo(() => {
    const suburbStats = new Map();

    Object.values(outputJsonModules).forEach((mod) => {
      const data = mod && typeof mod === 'object' && 'default' in mod ? mod.default : mod;
      const { items, fallbackSuburb } = toItems(data);

      items.forEach((item) => {
        if (!item || typeof item !== 'object') {
          return;
        }

        const suburb = getSuburb(item, fallbackSuburb);
        const price = getPrice(item);

        if (!suburb || !price) {
          return;
        }

        const current = suburbStats.get(suburb) || { total: 0, count: 0 };
        suburbStats.set(suburb, {
          total: current.total + price,
          count: current.count + 1,
        });
      });
    });

    return Array.from(suburbStats.entries())
      .map(([suburb, stats]) => ({
        suburb,
        averagePrice: stats.total / stats.count,
        samples: stats.count,
      }))
      .sort((a, b) => b.averagePrice - a.averagePrice)
      .slice(0, 5);
  }, []);

  return (
    <section className="mt-6">
      <div className="flex items-center justify-between mb-3">
        <h2 className="text-xs font-semibold text-gray-500 uppercase">Property Prices</h2>
        <span className="text-xs text-gray-400">Avg by suburb</span>
      </div>

      {suburbSummaries.length === 0 ? (
        <div className="rounded-lg border border-gray-200 bg-gray-50 p-3 text-sm text-gray-500">
          No property price records found in <code className="text-xs">/output</code>.
        </div>
      ) : (
        <div className="space-y-2">
          {suburbSummaries.map((summary) => (
            <div
              key={summary.suburb}
              className="rounded-lg border border-gray-200 bg-gradient-to-r from-white to-gray-50 p-3"
            >
              <div className="flex items-center justify-between">
                <p className="text-sm font-semibold text-gray-900">{formatSuburbLabel(summary.suburb)}</p>
                <p className="text-sm font-bold text-indigo-700">
                  {currencyFormatter.format(summary.averagePrice)}
                </p>
              </div>
              <p className="mt-1 text-xs text-gray-500">
                {summary.samples} {summary.samples === 1 ? 'sale' : 'sales'}
              </p>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

export default PropertyPriceCards;
