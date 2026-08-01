export function shouldForceSovereignRefresh(
  refreshNonce: number,
  consumedRefreshNonce: number,
) {
  return refreshNonce > consumedRefreshNonce;
}
