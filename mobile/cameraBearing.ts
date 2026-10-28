type Vector3 = { x: number; y: number; z: number };

function dot(a: Vector3, b: Vector3) {
  return a.x * b.x + a.y * b.y + a.z * b.z;
}

function normalize(vector: Vector3): Vector3 | null {
  const magnitude = Math.hypot(vector.x, vector.y, vector.z);
  if (!Number.isFinite(magnitude) || magnitude < 1e-6) return null;
  return { x: vector.x / magnitude, y: vector.y / magnitude, z: vector.z / magnitude };
}

export function cameraAxisBearing(
  magneticField: Vector3,
  gravity: Vector3,
  declinationDegrees: number,
): number | null {
  const up = normalize(gravity);
  if (!up || !Number.isFinite(declinationDegrees)) return null;

  const north = normalize({
    x: magneticField.x - dot(magneticField, up) * up.x,
    y: magneticField.y - dot(magneticField, up) * up.y,
    z: magneticField.z - dot(magneticField, up) * up.z,
  });
  if (!north) return null;

  const camera = { x: 0, y: 0, z: 1 };
  const horizontalCamera = normalize({
    x: camera.x - dot(camera, up) * up.x,
    y: camera.y - dot(camera, up) * up.y,
    z: camera.z - dot(camera, up) * up.z,
  });
  if (!horizontalCamera) return null;

  const east = normalize({
    x: north.y * up.z - north.z * up.y,
    y: north.z * up.x - north.x * up.z,
    z: north.x * up.y - north.y * up.x,
  });
  if (!east) return null;

  const magneticBearing = Math.atan2(dot(horizontalCamera, east), dot(horizontalCamera, north))
    * (180 / Math.PI);
  return (magneticBearing + declinationDegrees + 360) % 360;
}