import React, { useState } from 'react';

const ResultsTable = ({ results, summary }) => {
  const [expandedRow, setExpandedRow] = useState(null);
  const [sortConfig, setSortConfig] = useState({ key: null, direction: 'asc' });

  const handleSort = (key) => {
    let direction = 'asc';
    if (sortConfig.key === key && sortConfig.direction === 'asc') {
      direction = 'desc';
    }
    setSortConfig({ key, direction });
  };

  const sortedResults = [...results].sort((a, b) => {
    if (!sortConfig.key) return 0;

    const aValue = a[sortConfig.key];
    const bValue = b[sortConfig.key];

    if (typeof aValue === 'number' && typeof bValue === 'number') {
      return sortConfig.direction === 'asc' ? aValue - bValue : bValue - aValue;
    }

    const aStr = String(aValue || '').toLowerCase();
    const bStr = String(bValue || '').toLowerCase();

    if (sortConfig.direction === 'asc') {
      return aStr.localeCompare(bStr);
    }
    return bStr.localeCompare(aStr);
  });

  const exportToCSV = () => {
    const headers = [
      'Property Address',
      'Property Title',
      'Price',
      'Potential Purchase Price',
      'Renovation Budget',
      'Holding Costs',
      'Disposal Costs',
      'Contingency',
      'Potential Sale Price',
      'Profit',
      'Rental Yield %',
      'Weekly Rent Range',
      'Is Good Deal',
      'Has Stress Keywords',
    ];

    const rows = results.map((r) => [
      r.property_address || '',
      r.property_title || '',
      r.price || '',
      r.potential_purchase_price,
      r.renovation_budget,
      r.holding_costs,
      r.disposal_costs,
      r.contingency,
      r.potential_sale_price,
      r.profit,
      r.rental_yield_percentage ? `${r.rental_yield_percentage.toFixed(1)}%` : '',
      r.rental_yield_range ? `$${r.rental_yield_range[0]}-$${r.rental_yield_range[1]}/week` : '',
      r.is_good_deal ? 'Yes' : 'No',
      r.has_stress_keywords ? 'Yes' : 'No',
    ]);

    const csvContent = [
      headers.join(','),
      ...rows.map((row) => row.map((cell) => `"${cell}"`).join(',')),
    ].join('\n');

    const blob = new Blob([csvContent], { type: 'text/csv' });
    const url = window.URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'nz-propper-results.csv';
    a.click();
    window.URL.revokeObjectURL(url);
  };

  const formatCurrency = (value) => {
    return new Intl.NumberFormat('en-NZ', {
      style: 'currency',
      currency: 'NZD',
      minimumFractionDigits: 0,
      maximumFractionDigits: 0,
    }).format(value);
  };

  const getRowStyle = (result) => {
    const style = {};
    if (result.is_good_deal) {
      style.backgroundColor = '#e8f5e9';
      style.borderLeft = '4px solid #4CAF50';
    }
    if (result.has_stress_keywords) {
      style.backgroundColor = '#fff3e0';
      style.borderLeft = '4px solid #FF9800';
    }
    if (result.is_good_deal && result.has_stress_keywords) {
      style.backgroundColor = '#fff9c4';
      style.borderLeft = '4px solid #FBC02D';
    }
    return style;
  };

  return (
    <div>
      {summary && (
        <div
          style={{
            marginBottom: '1.5rem',
            padding: '1rem',
            backgroundColor: '#fff',
            borderRadius: '8px',
            boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
          }}
        >
          <h3 style={{ marginBottom: '0.5rem' }}>Summary</h3>
          <div style={{ display: 'flex', gap: '2rem', flexWrap: 'wrap' }}>
            <div>
              <strong>Total Properties:</strong> {summary.total_properties}
            </div>
            <div style={{ color: '#4CAF50' }}>
              <strong>Good Deals:</strong> {summary.good_deals_count}
            </div>
            <div style={{ color: '#FF9800' }}>
              <strong>Stress Sales:</strong> {summary.stress_sales_count}
            </div>
            <div>
              <strong>Duplicates Removed:</strong> {summary.duplicates_removed}
            </div>
          </div>
        </div>
      )}

      <div style={{ marginBottom: '1rem', display: 'flex', justifyContent: 'flex-end' }}>
        <button
          onClick={exportToCSV}
          style={{
            padding: '0.5rem 1rem',
            backgroundColor: '#2196F3',
            color: 'white',
            border: 'none',
            borderRadius: '4px',
            cursor: 'pointer',
            fontSize: '0.9rem',
          }}
        >
          Export to CSV
        </button>
      </div>

      <div
        style={{
          overflowX: 'auto',
          backgroundColor: '#fff',
          borderRadius: '8px',
          boxShadow: '0 2px 4px rgba(0,0,0,0.1)',
        }}
      >
        <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: '800px' }}>
          <thead>
            <tr style={{ backgroundColor: '#f5f5f5' }}>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  borderBottom: '2px solid #ddd',
                  cursor: 'pointer',
                }}
                onClick={() => handleSort('property_address')}
              >
                Property Address
                {sortConfig.key === 'property_address' && (
                  <span> {sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  borderBottom: '2px solid #ddd',
                  cursor: 'pointer',
                }}
                onClick={() => handleSort('property_title')}
              >
                Property Title
                {sortConfig.key === 'property_title' && (
                  <span> {sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'left',
                  borderBottom: '2px solid #ddd',
                }}
              >
                Price
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'right',
                  borderBottom: '2px solid #ddd',
                  cursor: 'pointer',
                }}
                onClick={() => handleSort('profit')}
              >
                Profit
                {sortConfig.key === 'profit' && (
                  <span> {sortConfig.direction === 'asc' ? '↑' : '↓'}</span>
                )}
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'center',
                  borderBottom: '2px solid #ddd',
                }}
              >
                Flags
              </th>
              <th
                style={{
                  padding: '0.75rem',
                  textAlign: 'center',
                  borderBottom: '2px solid #ddd',
                }}
              >
                Details
              </th>
            </tr>
          </thead>
          <tbody>
            {sortedResults.map((result, index) => (
              <React.Fragment key={index}>
                <tr
                  style={{
                    ...getRowStyle(result),
                    cursor: 'pointer',
                  }}
                  onClick={() => setExpandedRow(expandedRow === index ? null : index)}
                >
                  <td style={{ padding: '0.75rem', borderBottom: '1px solid #eee' }}>
                    {result.property_address || '-'}
                  </td>
                  <td style={{ padding: '0.75rem', borderBottom: '1px solid #eee' }}>
                    {result.property_title || '-'}
                  </td>
                  <td style={{ padding: '0.75rem', borderBottom: '1px solid #eee' }}>
                    {result.price || '-'}
                  </td>
                  <td
                    style={{
                      padding: '0.75rem',
                      borderBottom: '1px solid #eee',
                      textAlign: 'right',
                      fontWeight: 'bold',
                      color: result.profit >= 0 ? '#4CAF50' : '#f44336',
                    }}
                  >
                    {formatCurrency(result.profit)}
                  </td>
                  <td style={{ padding: '0.75rem', borderBottom: '1px solid #eee', textAlign: 'center' }}>
                    {result.is_good_deal && (
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.25rem 0.5rem',
                          backgroundColor: '#4CAF50',
                          color: 'white',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                          marginRight: '0.25rem',
                        }}
                      >
                        Good Deal
                      </span>
                    )}
                    {result.has_stress_keywords && (
                      <span
                        style={{
                          display: 'inline-block',
                          padding: '0.25rem 0.5rem',
                          backgroundColor: '#FF9800',
                          color: 'white',
                          borderRadius: '4px',
                          fontSize: '0.8rem',
                        }}
                      >
                        Stress Sale
                      </span>
                    )}
                  </td>
                  <td style={{ padding: '0.75rem', borderBottom: '1px solid #eee', textAlign: 'center' }}>
                    {expandedRow === index ? '▼' : '▶'}
                  </td>
                </tr>
                {expandedRow === index && (
                  <tr>
                    <td colSpan="6" style={{ padding: '1rem', backgroundColor: '#f9f9f9' }}>
                      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '1rem' }}>
                        <div>
                          <strong>Potential Purchase Price:</strong> {formatCurrency(result.potential_purchase_price)}
                        </div>
                        <div>
                          <strong>Renovation Budget:</strong> {formatCurrency(result.renovation_budget)}
                        </div>
                        <div>
                          <strong>Holding Costs:</strong> {formatCurrency(result.holding_costs)}
                        </div>
                        <div>
                          <strong>Disposal Costs:</strong> {formatCurrency(result.disposal_costs)}
                        </div>
                        <div>
                          <strong>Contingency:</strong> {formatCurrency(result.contingency)}
                        </div>
                        <div>
                          <strong>Potential Sale Price:</strong> {formatCurrency(result.potential_sale_price)}
                        </div>
                        {result.bedrooms && (
                          <div>
                            <strong>Bedrooms:</strong> {result.bedrooms}
                          </div>
                        )}
                        {result.bathrooms && (
                          <div>
                            <strong>Bathrooms:</strong> {result.bathrooms}
                          </div>
                        )}
                        {result.area && (
                          <div>
                            <strong>Area:</strong> {result.area}
                          </div>
                        )}
                        {result.rental_yield_percentage && (
                          <div>
                            <strong>Rental Yield:</strong> {result.rental_yield_percentage.toFixed(1)}%
                          </div>
                        )}
                        {result.rental_yield_range && (
                          <div>
                            <strong>Weekly Rent Range:</strong> ${result.rental_yield_range[0]} - ${result.rental_yield_range[1]} /week
                          </div>
                        )}
                        {result.property_link && (
                          <div style={{ gridColumn: '1 / -1' }}>
                            <strong>Property Link:</strong>{' '}
                            <a href={result.property_link} target="_blank" rel="noopener noreferrer">
                              {result.property_link}
                            </a>
                          </div>
                        )}
                      </div>
                    </td>
                  </tr>
                )}
              </React.Fragment>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
};

export default ResultsTable;


