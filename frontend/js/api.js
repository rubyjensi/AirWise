// API Client
export async function fetchHomeData(lat, lon, profile, activity, duration, locationName) {
  const params = new URLSearchParams({
    lat: lat.toString(),
    lon: lon.toString(),
    profile: profile,
    activity: activity,
    duration: duration.toString()
  });
  if (locationName) params.append('location_name', locationName);

  const res = await fetch(`/api/home?${params.toString()}`);
  if (!res.ok) throw new Error('Failed to fetch home telemetry');
  return await res.json();
}

export async function searchCities(query) {
  const res = await fetch(`/api/places/search?q=${encodeURIComponent(query)}`);
  if (!res.ok) return [];
  const data = await res.json();
  return data.results || [];
}
