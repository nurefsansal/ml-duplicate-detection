const TOKEN_KEY = "authToken";
const USERNAME_KEY = "authUsername";

export function getAuthToken(): string {
  return localStorage.getItem(TOKEN_KEY) || "";
}

export function setAuthSession(token: string, username: string): void {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USERNAME_KEY, username);
}

export function clearAuthSession(): void {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USERNAME_KEY);
}

export function getAuthUsername(): string {
  return localStorage.getItem(USERNAME_KEY) || "";
}

export function isAuthenticated(): boolean {
  return Boolean(getAuthToken());
}
