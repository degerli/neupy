import operator
from functools import reduce
from collections import namedtuple
from itertools import product

import numpy as np

from neupy.algorithms.minsearch import wolfe

from base import BaseTestCase


Case = namedtuple('Case', 'func_input func_expected')


class WolfeInterpolationTestCase(BaseTestCase):
    def assertAlmostEqual(self, left_value, right_value, places=6):
        if np.isnan(left_value) or np.isnan(right_value):
            self.assertTrue(np.isnan(left_value) and np.isnan(right_value))
        else:
            super(WolfeInterpolationTestCase, self).assertAlmostEqual(
                left_value, right_value, places
            )

    def test_line_search_exceptions(self):
        testcases = [
            # Invalid c1 values
            dict(c1=-1, c2=0.5, maxiter=1),
            dict(c1=0, c2=0.5, maxiter=1),
            dict(c1=1, c2=0.5, maxiter=1),

            # Invalid c2 values
            dict(c2=-1, c1=0.5, maxiter=1),
            dict(c2=0, c1=0.5, maxiter=1),
            dict(c2=1, c1=0.5, maxiter=1),

            # c1 > c2
            dict(c1=0.5, c2=0.1, maxiter=1),

            # Invalid `maxiter` values
            dict(c1=0.05, c2=0.1, maxiter=-10),
            dict(c1=0.05, c2=0.1, maxiter=0),
        ]

        def func(x):
            return x

        for testcase in testcases:
            error_desc = "Line search for {}".format(testcase)
            with self.assertRaises(ValueError, msg=error_desc):
                wolfe.line_search(f=func, f_deriv=func, **testcase)

    def test_sequential_and(self):
        for input_values in product([False, True], repeat=4):
            expected_value = reduce(operator.and_, input_values)
            actual_value = self.eval(wolfe.sequential_and(*input_values))
            self.assertEqual(expected_value, actual_value)

    def test_sequential_or(self):
        for input_values in product([False, True], repeat=4):
            expected_value = reduce(operator.or_, input_values)
            actual_value = self.eval(wolfe.sequential_or(*input_values))
            self.assertEqual(expected_value, actual_value)

    def test_quadratic_minimizer_exceptions(self):
        with self.assertRaises(ValueError):
            # Invalid value for parameter ``bound_size_ratio``
            wolfe.quadratic_minimizer(
                x_a=0, y_a=1,
                x_b=1, y_b=2,
                y_prime_a=-1,
                bound_size_ratio=2,
            )

    def test_quadratic_minimizer(self):
        testcases = (
            Case(
                func_input=dict(
                    y_prime_a=-1,
                    x_a=0, y_a=1,
                    x_b=1, y_b=2,
                ),
                func_expected=0.25,
            ),
            Case(
                func_input=dict(
                    y_prime_a=-1,
                    x_a=1, y_a=1,
                    x_b=2, y_b=2,
                ),
                func_expected=1.25,
            ),
        )

        for testcase in testcases:
            actual_output = wolfe.quadratic_minimizer(**testcase.func_input)
            self.assertAlmostEqual(
                self.eval(actual_output),
                testcase.func_expected,
            )

    def test_cubic_minimizer_exceptions(self):
        with self.assertRaisesRegexp(ValueError, "bound_size_ratio"):
            # bound_size_ratio < 0
            wolfe.cubic_minimizer(0, 1, -1, 5, 10, 10, 60, bound_size_ratio=-1)

        with self.assertRaisesRegexp(ValueError, "bound_size_ratio"):
            # bound_size_ratio >= 1
            wolfe.cubic_minimizer(0, 1, -1, 5, 10, 10, 60, bound_size_ratio=2)

    def test_cubic_minimizer(self):
        testcases = (
            Case(
                func_input=dict(
                    y_prime_a=-1.,
                    x_a=0., y_a=1.,
                    x_b=5., y_b=10.,
                    x_c=10., y_c=60.,
                    bound_size_ratio=0.2,
                ),
                func_expected=1.06,
            ),
        )

        for testcase in testcases:
            actual_output = wolfe.cubic_minimizer(**testcase.func_input)
            self.assertAlmostEqual(
                self.eval(actual_output),
                testcase.func_expected,
                places=2,
            )

    def test_wolfe_linear_search(self):
        x_current = 3
        grad = 2 * (x_current - 5.5)

        def square(step):
            x_new = x_current - step * grad
            return (x_new - 5.5) ** 2

        def square_deriv(step):
            # Derivative with respect to the step
            return -grad * 2 * ((x_current - step * grad) - 5.5)

        x_star = wolfe.line_search(square, square_deriv)
        x_star = self.eval(x_star)

        self.assertEqual(square(0), 6.25)
        self.assertAlmostEqual(square(x_star), 0, places=2)
        self.assertAlmostEqual(x_star, 0.5, places=2)
