import React from 'react';
import MapComponent from './components/MapComponent';
import './index.css';

function App() {
  return (
    <div className="flex h-screen w-screen overflow-hidden bg-gray-50 text-gray-900 font-sans">
      {/* Sidebar */}
      <aside className="w-96 bg-white/90 backdrop-blur-md shadow-xl z-10 flex flex-col border-r border-gray-200">
        <div className="p-6 border-b border-gray-100">
          <h1 className="text-2xl font-bold bg-gradient-to-r from-blue-600 to-indigo-600 bg-clip-text text-transparent">
            Brisbane Schools
          </h1>
          <p className="text-sm text-gray-500 mt-1">
            Catchment zones & property insights
          </p>
        </div>

        <div className="p-6 flex-1 overflow-y-auto">
          <div className="space-y-6">
            <div className="bg-blue-50 p-4 rounded-xl border border-blue-100">
              <h3 className="font-semibold text-blue-900 mb-2">Current Filters</h3>
              <div className="space-y-2 text-sm text-blue-800">
                <div className="flex justify-between">
                  <span>School Type:</span>
                  <span className="font-medium">Secondary (7-10)</span>
                </div>
                <div className="flex justify-between">
                  <span>Year:</span>
                  <span className="font-medium">2025</span>
                </div>
              </div>
            </div>

            <div className="text-sm text-gray-500">
              <p className="mb-2">Hover over a catchment zone to see school details and rankings.</p>
              <p>House price data loading...</p>
            </div>
          </div>
        </div>
      </aside>

      {/* Map Area */}
      <main className="flex-1 relative">
        <MapComponent />
      </main>
    </div>
  );
}

export default App;
