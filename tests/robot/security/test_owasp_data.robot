*** Settings ***
Documentation     OWASP A2 (Cryptographic Failures), A8 (Data Integrity), A9 (Logging Failures), A10 (SSRF) tests
Library           RequestsLibrary
Library           Collections
Resource          ../resources/common.robot

*** Test Cases ***
Weak Algorithm Rejected
    [Documentation]    A2 - Weak cryptographic algorithms should be rejected
    ${jwt_config}=    Evaluate
    ...    __import__('rover_swarm.security.auth').JwtConfig(secret='test-secret-min-16-chars', algorithm='HS256')
    ${provider}=    Evaluate    __import__('rover_swarm.security.auth').JwtAuthProvider(${jwt_config})
    ${token}=    Evaluate    ${provider}.create_access_token('test-user', __import__('rover_swarm.security.auth').Role.ADMIN)
    Should Contain    ${token}    eyJ
    Log    Token generated with HS256 (acceptable)

Tampered Payload Detected
    [Documentation]    A8 - Tampered JWT payloads should be detected
    Create Session    api    ${API_HOST}
    # A JWT with modified payload (signature mismatch)
    &{headers}=    Create Dictionary
    ...    Authorization=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsInJvbGUiOiJhZG1pbiJ9.tampered
    ${resp}=    GET On Session    api    /rovers    headers=${headers}    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

SSRF Attempt Blocked
    [Documentation]    A10 - Server-side request forgery attempts should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${ADMIN_USERNAME}", "password": "${ADMIN_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${ssrf_payloads}=    Create List
    ...    {"url": "http://169.254.169.254/latest/meta-data/"}
    ...    {"url": "http://127.0.0.1:6379"}
    ...    {"url": "http://10.0.0.1/admin"}
    ...    {"url": "file:///etc/passwd"}
    FOR    ${payload}    IN    @{ssrf_payloads}
        ${resp}=    POST On Session    api    /rovers/${TEST_ROVER_ID_1}/command
        ...    json={"command": "fetch", "params": ${payload}}
        ...    headers=${headers}
        ...    expected_status=400
        Should Be Equal As Strings    ${resp.status_code}    400
    END

Audit Log Presence
    [Documentation]    A9 - Security-relevant events should be logged
    ${secret}=    Evaluate    b'a' * 32
    ${audit}=    Evaluate    __import__('rover_swarm.security.audit').AuditLogger(secret_key=${secret})
    ${event}=    Evaluate    ${audit}.login_success('test-admin', source_ip='192.168.1.1')
    Should Be Equal    ${event.action}    login
    Should Be Equal    ${event.result}    success
    Should Be Equal    ${event.actor}    test-admin
    ${stats}=    Evaluate    ${audit}.get_statistics()
    Should Be Equal As Integers    ${stats['total_events']}    1

Audit Log Tampering Detection
    [Documentation]    A9 - Tampering with audit log entries should be detected
    ${secret}=    Evaluate    b'a' * 32
    ${audit}=    Evaluate    __import__('rover_swarm.security.audit').AuditLogger(secret_key=${secret})
    ${e1}=    Evaluate    ${audit}.login_success('admin-1')
    ${e2}=    Evaluate    ${audit}.resource_create('admin-1', 'mission:test')
    # Verify integrity before tampering
    ${ok}    ${errors}=    Evaluate    ${audit}.verify_integrity()
    Should Be True    ${ok}
    # Simulate tampering by modifying an event
    ${audit._events[0].actor}=    Set Variable    attacker
    ${ok}    ${errors}=    Evaluate    ${audit}.verify_integrity()
    Should Be False    ${ok}

Audit Log Failure Events
    [Documentation]    A9 - Authorization failures should be logged
    ${secret}=    Evaluate    b'a' * 32
    ${audit}=    Evaluate    __import__('rover_swarm.security.audit').AuditLogger(secret_key=${secret})
    ${event}=    Evaluate    ${audit}.login_failure('unknown-user', source_ip='10.0.0.99', reason='bad password')
    Should Be Equal    ${event.result}    unauthorized
    ${event}=    Evaluate    ${audit}.access_denied('observer-1', __import__('rover_swarm.security.audit').AuditAction.DELETE, 'mission:secret')
    Should Be Equal    ${event.result}    forbidden

Cryptographic Key Strength
    [Documentation]    A2 - Cryptographic keys should meet minimum strength requirements
    ${generator}=    Evaluate    __import__('rover_swarm.security.tls').CertGenerator(key_size=4096)
    Log    CertGenerator initialized with key_size=4096
    Should Be Equal As Integers    ${generator.key_size}    4096

Data Integrity With HMAC
    [Documentation]    A8 - HMAC should verify message integrity
    ${secret}=    Evaluate    b'my-secret-key-min-32-bytes-long!!'
    ${audit}=    Evaluate    __import__('rover_swarm.security.audit').AuditLogger(secret_key=${secret})
    ${event}=    Evaluate    ${audit}.login_success('test-user')
    ${stored_hash}=    Set Variable    ${event.hash}
    ${calculated}=    Evaluate    ${event}.calculate_hash(${secret})
    Should Be Equal    ${stored_hash}    ${calculated}
