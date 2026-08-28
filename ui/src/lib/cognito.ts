import {
  CognitoIdentityProviderClient,
  InitiateAuthCommand,
} from "@aws-sdk/client-cognito-identity-provider";

const REGION = import.meta.env.VITE_AWS_REGION || "us-east-1";
const CLIENT_ID = import.meta.env.VITE_COGNITO_CLIENT_ID;
const DEMO_EMAIL = import.meta.env.VITE_COGNITO_DEMO_EMAIL;
const DEMO_PASSWORD = import.meta.env.VITE_COGNITO_DEMO_PASSWORD;

if (!CLIENT_ID) {
  console.error("Falta VITE_COGNITO_CLIENT_ID en variables de entorno");
}

const cognitoClient = new CognitoIdentityProviderClient({ region: REGION });

function isTokenValid(token: string): boolean {
  try {
    const payloadBase64 = token.split(".")[1];
    if (!payloadBase64) return false;
    const jsonStr = atob(payloadBase64.replace(/-/g, "+").replace(/_/g, "/"));
    const payload = JSON.parse(jsonStr);
    if (!payload.exp) return false;
    // Check if token has at least 2 minutes of remaining validity
    return payload.exp * 1000 > Date.now() + 120_000;
  } catch {
    return false;
  }
}

export async function getCognitoAccessToken(
  email = DEMO_EMAIL,
  password = DEMO_PASSWORD,
  forceRefresh = false,
): Promise<string> {
  if (!CLIENT_ID || !email || !password) {
    throw new Error(
      "Credenciales de Cognito incompletas. Verifique VITE_COGNITO_CLIENT_ID, VITE_COGNITO_DEMO_EMAIL y VITE_COGNITO_DEMO_PASSWORD.",
    );
  }

  if (!forceRefresh) {
    const cached = sessionStorage.getItem("fintwit_access_token");
    if (cached && isTokenValid(cached)) {
      return cached;
    }
  }

  const command = new InitiateAuthCommand({
    AuthFlow: "USER_PASSWORD_AUTH",
    ClientId: CLIENT_ID,
    AuthParameters: {
      USERNAME: email,
      PASSWORD: password,
    },
  });

  const response = await cognitoClient.send(command);
  const token = response.AuthenticationResult?.AccessToken;
  if (!token) {
    throw new Error("No se pudo obtener el token de acceso de Cognito");
  }

  sessionStorage.setItem("fintwit_access_token", token);
  return token;
}
