(function (root, factory) {
    const api = factory();

    if (typeof module === "object" && module.exports) {
        module.exports = api;
    }

    root.RoutePlanner = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
    "use strict";

    function distance(a, b) {
        if (!a || !b) {
            return 0;
        }

        return Math.hypot(
            Number(a.x) - Number(b.x),
            Number(a.z) - Number(b.z)
        );
    }

    function routeDistance(points, start) {
        let total = 0,
            previous = start || null;

        for (const point of points) {
            if (previous) {
                total += distance(previous, point);
            }

            previous = point;
        }

        return total;
    }

    function nearestNeighbor(points, start) {
        const remaining = points.slice(),
            result = [];

        let previous = start || remaining[0] || null;

        if (!start && remaining.length) {
            result.push(remaining.shift());
        }

        while (remaining.length) {
            let best = 0,
                bestDistance = Infinity;

            for (let index = 0; index < remaining.length; index += 1) {
                const candidate = distance(previous, remaining[index]);

                if (candidate < bestDistance) {
                    best = index;
                    bestDistance = candidate;
                }
            }

            previous = remaining.splice(best, 1)[0];
            result.push(previous);
        }

        return result;
    }

    function travelCost(a, b, strategy) {
        let value = distance(a, b);

        if (!a || !b) {
            return value;
        }

        if (
            strategy === "region" &&
            a.region &&
            b.region &&
            a.region !== b.region
        ) {
            value += 2500;
        }

        if (strategy === "teleport") {
            const teleport = point =>
                Boolean(
                    point.teleport ||
                    [
                        "tours",
                        "sanctuaires",
                        "laboratoires_antiques"
                    ].includes(point.categorie)
                );

            if (teleport(a) || teleport(b)) {
                value *= 0.35;
            }

            if (a.region && b.region && a.region !== b.region) {
                value += 500;
            }
        }

        return value;
    }

    function nearestNeighborBy(points, start, strategy) {
        const remaining = points.slice(),
            result = [];

        let previous = start || remaining[0] || null;

        if (!start && remaining.length) {
            result.push(remaining.shift());
        }

        while (remaining.length) {
            let best = 0,
                bestCost = Infinity;

            for (let index = 0; index < remaining.length; index += 1) {
                const candidate = previous
                    ? travelCost(previous, remaining[index], strategy)
                    : index;

                if (candidate < bestCost) {
                    best = index;
                    bestCost = candidate;
                }
            }

            previous = remaining.splice(best, 1)[0];
            result.push(previous);
        }

        return result;
    }

    function twoOpt(points, start, maxPasses) {
        const route = points.slice();

        if (route.length < 4) {
            return route;
        }

        const passes = maxPasses ?? (route.length > 350 ? 1 : 8);

        for (let pass = 0; pass < passes; pass += 1) {
            let improved = false;

            for (let left = 0; left < route.length - 2; left += 1) {
                const before = left === 0 ? start : route[left - 1];

                if (!before) {
                    continue;
                }

                for (
                    let right = left + 1;
                    right < route.length;
                    right += 1
                ) {
                    const after =
                        right + 1 < route.length
                            ? route[right + 1]
                            : null;

                    const current =
                        distance(before, route[left]) +
                        (after ? distance(route[right], after) : 0);

                    const swapped =
                        distance(before, route[right]) +
                        (after ? distance(route[left], after) : 0);

                    if (swapped + 0.01 < current) {
                        route.splice(
                            left,
                            right - left + 1,
                            ...route
                                .slice(left, right + 1)
                                .reverse()
                        );

                        improved = true;
                    }
                }
            }

            if (!improved) {
                break;
            }
        }

        return route;
    }

    function optimize(points, start, strategy) {
        const route = points.slice();

        strategy = strategy || "distance";

        if (route.some(point => point.locked)) {
            const result = Array(route.length),
                remaining = route.filter(point => !point.locked);

            route.forEach((point, index) => {
                if (point.locked) {
                    result[index] = point;
                }
            });

            let previous = start || null;

            for (let index = 0; index < result.length; index += 1) {
                if (result[index]) {
                    previous = result[index];
                    continue;
                }

                let best = 0,
                    bestDistance = Infinity;

                for (
                    let candidate = 0;
                    candidate < remaining.length;
                    candidate += 1
                ) {
                    const value = previous
                        ? travelCost(
                            previous,
                            remaining[candidate],
                            strategy
                        )
                        : candidate;

                    if (value < bestDistance) {
                        best = candidate;
                        bestDistance = value;
                    }
                }

                result[index] = remaining.splice(best, 1)[0];
                previous = result[index];
            }

            return result;
        }

        const nearest =
            strategy === "distance"
                ? nearestNeighbor(route, start)
                : nearestNeighborBy(route, start, strategy);

        return strategy === "distance"
            ? twoOpt(nearest, start)
            : nearest;
    }

    function legs(points, start) {
        let previous = start || null,
            cumulative = 0;

        return points.map((point, index) => {
            const segment = previous
                ? distance(previous, point)
                : 0;

            cumulative += segment;
            previous = point;

            return {
                index: index + 1,
                point,
                distance: segment,
                cumulative
            };
        });
    }

    return {
        distance,
        routeDistance,
        travelCost,
        nearestNeighbor,
        nearestNeighborBy,
        twoOpt,
        optimize,
        legs
    };
});