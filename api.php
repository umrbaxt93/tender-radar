<?php
// Softy Platforma — High-Performance Hostinger WSGI Bridge
$py = "/opt/alt/python311/bin/python3";
$script = __DIR__ . "/wsgi_bridge.py";

$descriptorspec = [
    0 => ["pipe", "r"],  // stdin
    1 => ["pipe", "w"],  // stdout
    2 => ["pipe", "w"]   // stderr
];

$env = $_SERVER;
$env["PYTHONIOENCODING"] = "utf-8";

// Extract clean path for WSGI PATH_INFO
$uri = parse_url($env["REQUEST_URI"] ?? "/", PHP_URL_PATH);
// Remove any subfolder prefix if present
$env["PATH_INFO"] = $uri;

$process = proc_open("$py $script", $descriptorspec, $pipes, __DIR__, $env);

if (is_resource($process)) {
    // Write body to Python
    $input = fopen("php://input", "r");
    while (!feof($input)) {
        fwrite($pipes[0], fread($input, 8192));
    }
    fclose($input);
    fclose($pipes[0]);

    // Read headers & body from Python
    $stdout = $pipes[1];
    $isHeader = true;
    while (!feof($stdout)) {
        if ($isHeader) {
            $line = fgets($stdout);
            $trimmed = trim($line);
            if ($trimmed === "") {
                $isHeader = false;
                continue;
            }
            if (stripos($trimmed, "Status:") === 0) {
                $code = intval(trim(substr($trimmed, 7)));
                if ($code > 0) http_response_code($code);
            } else {
                header($trimmed);
            }
        } else {
            echo fread($stdout, 8192);
        }
    }
    fclose($pipes[1]);
    fclose($pipes[2]);
    proc_close($process);
} else {
    http_response_code(500);
    header("Content-Type: application/json; charset=utf-8");
    echo json_encode(["error" => "Failed to execute Python WSGI bridge"]);
}
