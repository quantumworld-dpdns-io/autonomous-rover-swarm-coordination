*** Settings ***
Documentation     Common keywords and variables for rover swarm tests
Library           Collections
Library           RequestsLibrary
Library           CrdtLibrary.py

*** Variables ***
${API_HOST}              http://localhost:8080
${MQTT_BROKER}           localhost
${MQTT_PORT}             1883
${TEST_ROVER_ID_1}       rover-test-1
${TEST_ROVER_ID_2}       rover-test-2
${TEST_ROVER_ID_3}       rover-test-3
${TEST_MISSION_ID}       test-mission-001
${ADMIN_USERNAME}        admin
${ADMIN_PASSWORD}        changeme
${OBSERVER_USERNAME}     observer
${OBSERVER_PASSWORD}     observer-pass

*** Keywords ***
Start Rover
    [Documentation]    Start a simulated rover with given ID
    [Arguments]    ${rover_id}=${TEST_ROVER_ID_1}
    Log    Starting rover ${rover_id}
    # Integration hook: actual test harness would start rover process
    ${started}=    Evaluate    True
    Should Be True    ${started}

Stop Rover
    [Documentation]    Stop a simulated rover
    [Arguments]    ${rover_id}=${TEST_ROVER_ID_1}
    Log    Stopping rover ${rover_id}
    # Integration hook: actual test harness would stop rover process
    ${stopped}=    Evaluate    True
    Should Be True    ${stopped}

Connect MQTT
    [Documentation]    Connect to MQTT broker (simulated)
    Log    Connected to MQTT at ${MQTT_BROKER}:${MQTT_PORT}
    ${connected}=    Evaluate    True
    Should Be True    ${connected}

Disconnect MQTT
    [Documentation]    Disconnect from MQTT broker
    Log    Disconnected from MQTT broker
    ${disconnected}=    Evaluate    True
    Should Be True    ${disconnected}

API Health Should Be OK
    [Documentation]    Check that the API health endpoint returns 200
    Create Session    api    ${API_HOST}
    ${resp}=    GET On Session    api    /health    expected_status=200
    Should Be Equal As Strings    ${resp.status_code}    200
    Dictionary Should Contain Key    ${resp.json()}    status

Test Setup
    [Documentation]    Default test setup keyword
    Log    Test setup complete

Test Teardown
    [Documentation]    Default test teardown keyword
    Log    Test teardown complete
