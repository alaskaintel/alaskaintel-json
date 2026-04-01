const { chromium } = require('playwright');

(async () => {
    let browser;
    try {
        browser = await chromium.launch({ headless: true });
        const page = await browser.newPage({
            userAgent: "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
        });
        
        const results = [];

        // 1. Scrape ADF&G
        try {
            await page.goto('https://adfg.alaska.gov/index.cfm?adfg=newsreleases.main', { waitUntil: 'domcontentloaded', timeout: 20000 });
            
            // Wait a moment for any WAF JS challenges
            await page.waitForTimeout(2000);
            
            // Extract links from the main content area
            const adfgItems = await page.$$eval('a', links => {
                return links.map(l => ({ title: l.innerText.trim(), link: l.href }))
                            .filter(l => l.link.includes('adfg.alaska.gov') && l.title.length > 15 && !l.title.includes('Subscribe'));
            });
            
            let count = 0;
            for (let item of adfgItems) {
                if (count >= 20) break;
                // Basic filtering for actual articles
                if (item.title.toLowerCase().includes('emergency order') || item.title.toLowerCase().includes('advisory') || item.title.toLowerCase().includes('release')) {
                    results.push({
                        title: item.title,
                        link: item.link,
                        source: "ADF&G Press Releases",
                        timestamp: new Date().toISOString() 
                    });
                    count++;
                }
            }
        } catch(e) { /* ignore and continue */ }

        // 2. Scrape USFWS
        try {
            await page.goto('https://www.fws.gov/press-release', { waitUntil: 'domcontentloaded', timeout: 20000 });
            await page.waitForTimeout(2000);

            // Extract articles
            const fwsItems = await page.$$eval('a', links => {
                return links.map(l => ({ title: l.innerText.trim(), link: l.href }))
                            .filter(l => l.link.includes('fws.gov/press-release/') && l.title.length > 15);
            });
            
            let count = 0;
            for (let item of fwsItems) {
                if (count >= 20) break;
                results.push({
                    title: item.title,
                    link: item.link,
                    source: "US Fish & Wildlife Service",
                    timestamp: new Date().toISOString() 
                });
                count++;
            }
        } catch(e) { /* ignore */ }

        console.log(JSON.stringify(results));
        
    } catch(err) {
        console.error(err);
    } finally {
        if (browser) await browser.close();
    }
})();
