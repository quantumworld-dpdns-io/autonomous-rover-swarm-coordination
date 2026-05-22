*** Settings ***
Documentation     OWASP A1 (Broken Access Control) and A7 (Authentication Failures) tests
Library           RequestsLibrary
Library           Collections
Resource          ../resources/common.robot

*** Test Cases ***
Unauthenticated Access To Protected Endpoints
    [Documentation]    A1 - Protected endpoints should reject unauthenticated requests
    Create Session    api    ${API_HOST}
    ${endpoints}=    Create List
    ...    /rovers    /missions    /auth/admin    /swarm/config
    FOR    ${ep}    IN    @{endpoints}
        ${resp}=    GET On Session    api    ${ep}    expected_status=401
        Should Be Equal As Strings    ${resp.status_code}    401
    END

Invalid Token Rejected
    [Documentation]    A7 - Requests with invalid JWT should be rejected
    Create Session    api    ${API_HOST}
    &{headers}=    Create Dictionary    Authorization=Bearer invalid-token-here
    ${resp}=    GET On Session    api    /rovers    headers=${headers}    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

Expired Token Rejected
    [Documentation]    A7 - Requests with expired JWT should be rejected
    Create Session    api    ${API_HOST}
    &{headers}=    Create Dictionary    Authorization=Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJhZG1pbiIsImV4cCI6MTUxNjIzOTAyMn0.
    ${resp}=    GET On Session    api    /rovers    headers=${headers}    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

Malformed Token Rejected
    [Documentation]    A7 - Malformed authorization headers should be rejected
    Create Session    api    ${API_HOST}
    &{headers}=    Create Dictionary    Authorization=not-a-bearer-token
    ${resp}=    GET On Session    api    /missions    headers=${headers}    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

Brute Force Detection
    [Documentation]    A7 - Multiple failed login attempts should trigger rate limiting
    Create Session    api    ${API_HOST}
    FOR    ${i}    IN RANGE    10
        ${resp}=    POST On Session    api    /auth/login
        ...    json={"username": "admin", "password": "wrong-password-${i}"}
        ...    expected_status=401
        Should Be Equal As Strings    ${resp.status_code}    401
    END
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "admin", "password": "wrong-again"}
    ...    expected_status=429
    Should Be Equal As Strings    ${resp.status_code}    429

Role Escalation Attempt
    [Documentation]    A1 - Observer should not escalate to admin operations
    Create Session    api    ${API_HOST}
    # Login as observer
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${OBSERVER_USERNAME}", "password": "${OBSERVER_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    # Observer should not be able to delete missions
    ${resp}=    DELETE On Session    api    /missions/some-mission    headers=${headers}    expected_status=403
    Should Be Equal As Strings    ${resp.status_code}    403

Access Control On Rover Commands
    [Documentation]    A1 - Unauthorized users should not send rover commands
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${OBSERVER_USERNAME}", "password": "${OBSERVER_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${resp}=    POST On Session    api    /rovers/${TEST_ROVER_ID_1}/command
    ...    json={"command": "shutdown"}
    ...    headers=${headers}
    ...    expected_status=403
    Should Be Equal As Strings    ${resp.status_code}    403

Missing Authorization Header
    [Documentation]    A7 - Requests without any Authorization header should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    GET On Session    api    /auth/admin    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401
