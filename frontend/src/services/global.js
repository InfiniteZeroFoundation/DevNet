export async function resetAll() {
    const res = await fetch("http://localhost:8000/reset/resetall");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }
  
  export async function distributeDataset() {
    const res = await fetch("http://localhost:8000/distribute/dataset");
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    return await res.json();
  }
  