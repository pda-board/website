<?php
// Deploy hook for pda-tue.nl (Plesk).
//
// GitHub cannot reach the Plesk Git webhook directly (port 8443 is only open
// inside the TU/e network), so GitHub calls this page instead and this page
// asks Plesk, from the server itself, to pull the repository.
//
// Configuration lives OUTSIDE the web root, in ../deploy-hook-config.php
// (created by hand in the Plesk File Manager, never committed):
//
//   <?php return [
//     'plesk_hook' => 'https://…:8443/modules/git/public/web-hook.php?uuid=…',
//     'secret'     => '…same secret as in the GitHub webhook settings…',
//   ];

header('Content-Type: text/plain; charset=utf-8');

if ($_SERVER['REQUEST_METHOD'] !== 'POST') {
    http_response_code(405);
    exit("POST only.\n");
}

$configFile = dirname(__DIR__) . '/deploy-hook-config.php';
$config = is_readable($configFile) ? require $configFile : null;
if (!is_array($config) || !is_string($config['secret'] ?? null) || strlen($config['secret']) < 20
        || !is_string($config['plesk_hook'] ?? null)) {
    http_response_code(503);
    exit("Unavailable.\n");
}

$payload = file_get_contents('php://input');
$given = $_SERVER['HTTP_X_HUB_SIGNATURE_256'] ?? '';
$expected = 'sha256=' . hash_hmac('sha256', $payload, $config['secret']);
if (!hash_equals($expected, $given)) {
    http_response_code(403);
    exit("Bad signature.\n");
}

$event = $_SERVER['HTTP_X_GITHUB_EVENT'] ?? '';
if ($event === 'ping') {
    exit("pong\n");
}
if ($event !== 'push') {
    exit("Ignored event: $event\n");
}

$ch = curl_init($config['plesk_hook']);
curl_setopt_array($ch, [
    CURLOPT_POST => true,
    CURLOPT_POSTFIELDS => $payload,
    CURLOPT_HTTPHEADER => [
        'Content-Type: application/json',
        'X-GitHub-Event: push',
    ],
    CURLOPT_RETURNTRANSFER => true,
    CURLOPT_TIMEOUT => 60,
    // The Plesk host is fixed in the server-side config; its certificate is
    // issued for the internal host name, so skip verification for this call.
    CURLOPT_SSL_VERIFYPEER => false,
    CURLOPT_SSL_VERIFYHOST => 0,
]);
$body = curl_exec($ch);
$code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
$error = curl_error($ch);
curl_close($ch);

if ($body === false) {
    http_response_code(502);
    exit("Could not reach Plesk: $error\n");
}
http_response_code($code >= 200 && $code < 300 ? 200 : 502);
echo "Plesk answered $code\n";
