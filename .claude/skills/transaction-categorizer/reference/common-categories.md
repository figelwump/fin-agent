# Category Taxonomy Guidelines

⚠️ **CRITICAL: ALWAYS Load User's Taxonomy First**

Before suggesting any categories, ALWAYS run:
```bash
fin-query saved categories --limit 200 --format csv
```

This shows the user's actual category structure. **Use these categories first** - only reference the suggested categories below as a fallback if the user's taxonomy is empty or doesn't contain a suitable match.

Never suggest creating new categories without first checking if an existing category fits. This prevents taxonomy bloat.

---

Suggested Categories (ONLY use as fallback when user taxonomy is empty)

Food & Dining
- Restaurants
- Fast Food
- Coffee Shops
- Groceries
- Bars & Nightlife

Shopping
- Online
- Clothing
- Electronics
- Home & Garden
- Sporting Goods

Transportation
- Gas & Fuel
- Public Transportation
- Parking
- Ride Share
- Auto Maintenance

Bills & Utilities
- Phone
- Internet
- Electric
- Water
- Trash/Recycling

Entertainment
- Movies & Streaming
- Music
- Sports
- Hobbies
- Books

Healthcare
- Doctor
- Dentist
- Pharmacy
- Vision

Financial
- Bank Fees
- Interest Charges
- ATM Fees
- Service Charges

Income
- Salary/Paycheck
- Reimbursement
- Refund

Preventing Taxonomy Bloat
- Prefer existing categories; suggest close matches
- Confirm with the user before creating new ones
