import React from 'react';

const CalculatorMode = ({ mode, onModeChange }) => {
  return (
    <div style={{ marginBottom: '2rem' }}>
      <h2 style={{ marginBottom: '1rem', fontSize: '1.5rem' }}>Calculator Mode</h2>
      <div style={{ display: 'flex', gap: '1rem' }}>
        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
          <input
            type="radio"
            name="mode"
            value="flip"
            checked={mode === 'flip'}
            onChange={(e) => onModeChange(e.target.value)}
            style={{ marginRight: '0.5rem' }}
          />
          <span style={{ fontSize: '1.1rem' }}>Flip</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
          <input
            type="radio"
            name="mode"
            value="flip-or-rent"
            checked={mode === 'flip-or-rent'}
            onChange={(e) => onModeChange(e.target.value)}
            style={{ marginRight: '0.5rem' }}
          />
          <span style={{ fontSize: '1.1rem' }}>Flip Or Rent</span>
        </label>
        <label style={{ display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
          <input
            type="radio"
            name="mode"
            value="rental"
            checked={mode === 'rental'}
            onChange={(e) => onModeChange(e.target.value)}
            style={{ marginRight: '0.5rem' }}
          />
          <span style={{ fontSize: '1.1rem' }}>Rental</span>
        </label>
      </div>
    </div>
  );
};

export default CalculatorMode;


