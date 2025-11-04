// Placeholder data generators for screenshot mode
// Used to hide sensitive financial data when taking screenshots

const merchants = [
  'Coffee Shop', 'Grocery Store', 'Gas Station', 'Restaurant',
  'Online Store', 'Pharmacy', 'Department Store', 'Tech Store'
];

const categories = [
  'Food & Dining', 'Groceries', 'Transportation', 'Shopping',
  'Entertainment', 'Bills & Utilities', 'Health', 'Travel'
];

export function getPlaceholderMerchant(index: number = 0): string {
  return merchants[index % merchants.length];
}

export function getPlaceholderCategory(index: number = 0): string {
  return categories[index % categories.length];
}

export function getPlaceholderAmount(index: number = 0): string {
  const amounts = ['$12.50', '$45.99', '$8.75', '$123.45', '$67.89', '$34.12', '$89.99', '$15.00'];
  return amounts[index % amounts.length];
}

export function getPlaceholderDate(daysAgo: number = 0): string {
  if (daysAgo === 0) return 'Today';
  if (daysAgo === 1) return 'Yesterday';
  if (daysAgo < 7) return `${daysAgo}d ago`;
  if (daysAgo < 30) return `${Math.floor(daysAgo / 7)}w ago`;
  return `${Math.floor(daysAgo / 30)}mo ago`;
}

export function getPlaceholderDescription(index: number = 0): string {
  const descriptions = [
    'Purchase at local store',
    'Monthly subscription payment',
    'Grocery shopping',
    'Fuel purchase',
    'Online order',
    'Dining out',
    'Utility payment',
    'Healthcare expense'
  ];
  return descriptions[index % descriptions.length];
}
