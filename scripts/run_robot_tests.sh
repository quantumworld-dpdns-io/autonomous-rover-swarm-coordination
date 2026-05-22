#!/usr/bin/env bash
set -euo pipefail

PROJECT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$PROJECT_DIR"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

print_usage() {
    cat <<EOF
Usage: $(basename "$0") [OPTIONS]

Run Robot Framework tests for the rover-swarm platform.

Options:
  -s, --suite SUITE      Run specific test suite (api, mqtt, security, simulation)
  -i, --include TAG      Include tests with given tag (can be used multiple times)
  -e, --exclude TAG      Exclude tests with given tag (can be used multiple times)
  -d, --output-dir DIR   Output directory (default: reports/robot)
  -v, --variable NAME:V   Set Robot variable
  -p, --parallel N       Run tests in parallel with N processes (requires pabot)
  -c, --ci               CI mode: start/stop Docker Compose automatically
  -h, --help             Show this help message

Examples:
  $(basename "$0") --suite api
  $(basename "$0") --include smoke --exclude slow
  $(basename "$0") --ci --parallel 4
  $(basename "$0") --variable API_HOST:10.0.0.1

Requirements:
  - Python 3.12+ with robotframework installed
  - Docker Compose (if using --ci flag)
  - Access to MQTT broker, API, and other services
EOF
}

SUITE=""
INCLUDE_TAGS=()
EXCLUDE_TAGS=()
OUTPUT_DIR="reports/robot"
VARIABLES=()
PARALLEL=""
CI_MODE=false

while [[ $# -gt 0 ]]; do
    case "$1" in
        -s|--suite)
            SUITE="$2"
            shift 2
            ;;
        -i|--include)
            INCLUDE_TAGS+=("$2")
            shift 2
            ;;
        -e|--exclude)
            EXCLUDE_TAGS+=("$2")
            shift 2
            ;;
        -d|--output-dir)
            OUTPUT_DIR="$2"
            shift 2
            ;;
        -v|--variable)
            VARIABLES+=("$2")
            shift 2
            ;;
        -p|--parallel)
            PARALLEL="$2"
            shift 2
            ;;
        -c|--ci)
            CI_MODE=true
            shift
            ;;
        -h|--help)
            print_usage
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            print_usage
            exit 1
            ;;
    esac
done

cleanup() {
    local exit_code=$?
    if [ "$CI_MODE" = true ]; then
        echo -e "\n${YELLOW}Tearing down Docker Compose environment...${NC}"
        docker compose -f docker-compose.yml down -v --remove-orphans 2>/dev/null || true
    fi
    exit "$exit_code"
}
trap cleanup EXIT INT TERM

if [ "$CI_MODE" = true ]; then
    echo -e "${BLUE}Starting Docker Compose environment...${NC}"
    docker compose -f docker-compose.yml up -d --wait --wait-timeout 120

    echo -e "${BLUE}Waiting for services to be healthy...${NC}"
    echo "Waiting for MQTT broker..."
    for i in $(seq 1 30); do
        nc -z localhost 1883 && echo "  MQTT broker ready" && break
        sleep 2
    done
    echo "Waiting for ChromaDB..."
    for i in $(seq 1 30); do
        curl -sf http://localhost:8000/api/v1/heartbeat > /dev/null 2>&1 && echo "  ChromaDB ready" && break
        sleep 2
    done
    echo -e "${GREEN}All services ready${NC}"
fi

mkdir -p "$OUTPUT_DIR"

ROBOT_ARGS=()
ROBOT_ARGS+=(--outputdir "$OUTPUT_DIR")
ROBOT_ARGS+=(--timestampoutputs)
ROBOT_ARGS+=(--log log.html)
ROBOT_ARGS+=(--report report.html)
ROBOT_ARGS+=(--output output.xml)
ROBOT_ARGS+=(--xunit xunit.xml)

# Default variables
ROBOT_ARGS+=(--variable BROKER_HOST:localhost)
ROBOT_ARGS+=(--variable API_HOST:localhost)
ROBOT_ARGS+=(--variable API_PORT:8080)
ROBOT_ARGS+=(--variable MQTT_PORT:1883)
ROBOT_ARGS+=(--variable WS_PORT:9001)
ROBOT_ARGS+=(--variable CHROMA_HOST:localhost)
ROBOT_ARGS+=(--variable CHROMA_PORT:8000)

for var in "${VARIABLES[@]}"; do
    ROBOT_ARGS+=(--variable "$var")
done

if [ -n "$SUITE" ]; then
    ROBOT_ARGS+=(--include "$SUITE")
fi

for tag in "${INCLUDE_TAGS[@]}"; do
    ROBOT_ARGS+=(--include "$tag")
done

for tag in "${EXCLUDE_TAGS[@]}"; do
    ROBOT_ARGS+=(--exclude "$tag")
done

ROBOT_ARGS+=(tests/robot/)

echo -e "${BLUE}Running Robot Framework tests...${NC}"
echo "Output directory: $OUTPUT_DIR"
if [ -n "$SUITE" ]; then
    echo "Test suite: $SUITE"
fi
if [ ${#INCLUDE_TAGS[@]} -gt 0 ]; then
    echo "Included tags: ${INCLUDE_TAGS[*]}"
fi
if [ ${#EXCLUDE_TAGS[@]} -gt 0 ]; then
    echo "Excluded tags: ${EXCLUDE_TAGS[*]}"
fi
echo ""

if [ -n "$PARALLEL" ]; then
    if command -v pabot &>/dev/null; then
        echo -e "${BLUE}Running tests in parallel with $PARALLEL processes...${NC}"
        pabot --processes "$PARALLEL" "${ROBOT_ARGS[@]}"
    else
        echo -e "${YELLOW}pabot not found. Install with: pip install robotframework-pabot${NC}"
        echo -e "${YELLOW}Falling back to sequential execution...${NC}"
        robot "${ROBOT_ARGS[@]}"
    fi
else
    robot "${ROBOT_ARGS[@]}"
fi

ROBOT_EXIT_CODE=$?

if [ $ROBOT_EXIT_CODE -eq 0 ]; then
    echo -e "\n${GREEN}✓ All Robot Framework tests passed!${NC}"
elif [ $ROBOT_EXIT_CODE -eq 1 ]; then
    echo -e "\n${YELLOW}⚠ Some Robot Framework tests failed${NC}"
elif [ $ROBOT_EXIT_CODE -eq 2 ]; then
    echo -e "\n${RED}✗ Robot Framework test execution error${NC}"
fi

echo ""
echo -e "${BLUE}Reports:${NC}"
echo "  HTML Report:  file://$PROJECT_DIR/$OUTPUT_DIR/report.html"
echo "  Log:          file://$PROJECT_DIR/$OUTPUT_DIR/log.html"
echo "  XML Output:   $OUTPUT_DIR/output.xml"

exit "$ROBOT_EXIT_CODE"
