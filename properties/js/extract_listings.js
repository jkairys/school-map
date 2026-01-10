// Extract property listings from search results page
(() => {
    const listings = [];
    const cards = document.querySelectorAll('[class*="PropertyCardSearch__propertyCard--"]');

    cards.forEach((card, index) => {
        try {
            const listing = {
                url: '',
                address: '',
                price: '',
                beds: null,
                baths: null,
                parking: null,
                soldDate: '',
                propertyType: 'House',
                agentName: '',
                agencyName: ''
            };

            const link = card.querySelector('a[href*="/property/"]');
            if (link) {
                listing.url = link.href;
            }

            const ribbon = card.querySelector('[class*="recentlySold"]');
            if (ribbon) {
                listing.soldDate = ribbon.textContent.trim();
            }

            const priceEl = card.querySelector('[class*="propertyCardPrice"]');
            if (priceEl) {
                listing.price = priceEl.textContent.trim();
            }

            const addressEls = card.querySelectorAll('[class*="propertyCardAddressText"]');
            if (addressEls.length > 0) {
                listing.address = Array.from(addressEls).map(el => el.textContent.trim()).join(' ').replace(/,\s*$/, '');
            }

            const attrsEl = card.querySelector('[class*="propertyCardAttributes"]');
            if (attrsEl) {
                const bedsMatch = attrsEl.textContent.match(/Bedrooms[:\s]*?(\d+)/i);
                const bathsMatch = attrsEl.textContent.match(/Bathrooms[:\s]*?(\d+)/i);
                const carsMatch = attrsEl.textContent.match(/Car\s*spaces[:\s]*?(\d+)/i);

                if (bedsMatch) listing.beds = parseInt(bedsMatch[1]);
                if (bathsMatch) listing.baths = parseInt(bathsMatch[1]);
                if (carsMatch) listing.parking = parseInt(carsMatch[1]);
            }

            const typeMatch = card.textContent.match(/Type[:\s]*?(House|Apartment|Townhouse|Land|Unit)/i);
            if (typeMatch) {
                listing.propertyType = typeMatch[1];
            }

            const agentEl = card.querySelector('[class*="agentRep"]');
            if (agentEl) {
                const nameEl = agentEl.querySelector('.bold500, [class*="bold"]');
                if (nameEl) {
                    listing.agentName = nameEl.textContent.trim();
                }
                const agencyEl = agentEl.querySelector('[class*="agencyName"]');
                if (agencyEl) {
                    listing.agencyName = agencyEl.textContent.trim();
                }
            }

            if (listing.address || listing.url) {
                listings.push(listing);
            }
        } catch (e) {
            console.error('Error parsing card ' + index + ': ' + e);
        }
    });

    return listings;
})();
