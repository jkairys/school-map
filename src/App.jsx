import React from 'react';
import MapComponent from './components/MapComponent';
import './index.css';

function App() {
  const [hoveredSchool, setHoveredSchool] = React.useState(null);
  const [selectedCompetency, setSelectedCompetency] = React.useState('Reading');
  const [showCatchments, setShowCatchments] = React.useState(true);
  const [showSchoolLocations, setShowSchoolLocations] = React.useState(true);
  const [showRailwayStations, setShowRailwayStations] = React.useState(true);

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

          <div className="mt-4 space-y-4">
            <div>
              <label htmlFor="competency" className="block text-xs font-semibold text-gray-500 mb-1 uppercase">
                NAPLAN Competency
              </label>
              <select
                id="competency"
                className="block w-full pl-3 pr-10 py-2 text-sm border-gray-300 focus:outline-none focus:ring-indigo-500 focus:border-indigo-500 sm:text-sm rounded-md border"
                value={selectedCompetency}
                onChange={(e) => setSelectedCompetency(e.target.value)}
              >
                {['Reading', 'Writing', 'Spelling', 'Grammar', 'Numeracy'].map((comp) => (
                  <option key={comp} value={comp}>
                    {comp}
                  </option>
                ))}
              </select>
              <p className="text-xs text-gray-400 mt-1">
                Map colors compare schools to state average.
              </p>
            </div>

            <div>
              <label className="block text-xs font-semibold text-gray-500 mb-2 uppercase">
                Map Layers
              </label>
              <div className="space-y-4">
                {/* Junior Secondary Group */}
                <div>
                  <div className="flex items-center space-x-2">
                    <input
                      type="checkbox"
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      checked={showCatchments && showSchoolLocations}
                      ref={input => {
                        if (input) {
                          input.indeterminate = (showCatchments || showSchoolLocations) && !(showCatchments && showSchoolLocations);
                        }
                      }}
                      onChange={(e) => {
                        const checked = e.target.checked;
                        setShowCatchments(checked);
                        setShowSchoolLocations(checked);
                      }}
                    />
                    <span className="text-sm font-medium text-gray-900">Junior Secondary</span>
                  </div>

                  <div className="ml-6 mt-2 space-y-2 border-l-2 border-gray-100 pl-3">
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showCatchments}
                        onChange={(e) => setShowCatchments(e.target.checked)}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">Catchments</span>
                    </label>
                    <label className="flex items-center space-x-2 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={showSchoolLocations}
                        onChange={(e) => setShowSchoolLocations(e.target.checked)}
                        className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                      />
                      <span className="text-sm text-gray-700">Locations</span>
                    </label>
                  </div>
                </div>
              </div>

              {/* Transport Group */}
              <div className="mt-6">
                <div className="flex items-center space-x-2">
                  <input
                    type="checkbox"
                    className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    checked={showRailwayStations}
                    onChange={(e) => setShowRailwayStations(e.target.checked)}
                  />
                  <span className="text-sm font-medium text-gray-900">Transport</span>
                </div>

                <div className="ml-6 mt-2 space-y-2 border-l-2 border-gray-100 pl-3">
                  <label className="flex items-center space-x-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={showRailwayStations}
                      onChange={(e) => setShowRailwayStations(e.target.checked)}
                      className="rounded border-gray-300 text-indigo-600 focus:ring-indigo-500"
                    />
                    <span className="text-sm text-gray-700">Railway Stations</span>
                  </label>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div className="p-6 flex-1 overflow-y-auto">
          {hoveredSchool ? (
            <div className="space-y-6">
              <div>
                <h2 className="text-xl font-bold text-gray-900 leading-tight">
                  {hoveredSchool.schoolName || hoveredSchool.name}
                </h2>
                <div className="mt-1 flex flex-wrap gap-2">
                  <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                    Gov
                  </span>
                  {hoveredSchool.profile?.icsea && (
                    <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                      ICSEA: {hoveredSchool.profile.icsea}
                    </span>
                  )}
                </div>
              </div>

              {hoveredSchool.profile && (
                <div className="grid grid-cols-2 gap-4">
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500 uppercase font-semibold">Enrolments</p>
                    <p className="text-lg font-bold text-gray-900">{hoveredSchool.profile.totalEnrolments || 'N/A'}</p>
                  </div>
                  <div className="bg-gray-50 p-3 rounded-lg">
                    <p className="text-xs text-gray-500 uppercase font-semibold">Indigenous</p>
                    <p className="text-lg font-bold text-gray-900">{hoveredSchool.profile.indigenousPercent ? `${hoveredSchool.profile.indigenousPercent}%` : 'N/A'}</p>
                  </div>
                </div>
              )}

              {hoveredSchool.naplan && (
                <div>
                  <h3 className="font-semibold text-gray-900 mb-3 flex items-center">
                    <span className="w-1.5 h-1.5 bg-indigo-500 rounded-full mr-2"></span>
                    NAPLAN Results
                  </h3>
                  <div className="overflow-x-auto">
                    <table className="min-w-full text-xs text-left">
                      <thead>
                        <tr className="bg-gray-50 border-b border-gray-100">
                          {hoveredSchool.naplan[0].map((header, i) => (
                            <th key={i} className="py-2 px-2 font-semibold text-gray-600 first:pl-2 last:pr-2">
                              {header === "" ? "Year" : header}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {hoveredSchool.naplan.slice(1).map((row, i) => (
                          <tr key={i} className="border-b border-gray-50 hover:bg-gray-50/50">
                            {row.map((cell, j) => (
                              <td key={j} className={`py-2 px-2 ${j === 0 ? 'font-medium text-gray-900' : 'text-gray-600'}`}>
                                {cell}
                              </td>
                            ))}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </div>
              )}

              {!hoveredSchool.naplan && (
                <div className="p-4 bg-yellow-50 text-yellow-800 text-sm rounded-lg">
                  No NAPLAN data available for this school.
                </div>
              )}

            </div>
          ) : (
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

              <div className="text-sm text-gray-500 text-center py-10">
                <p className="mb-2">Hover over a catchment zone to see school details.</p>
              </div>
            </div>
          )}
        </div>
      </aside>

      {/* Map Area */}
      <main className="flex-1 relative">
        <MapComponent
          onSchoolHover={setHoveredSchool}
          selectedCompetency={selectedCompetency}
          showCatchments={showCatchments}
          showSchoolLocations={showSchoolLocations}
          showRailwayStations={showRailwayStations}
        />
      </main>
    </div>
  );
}

export default App;
