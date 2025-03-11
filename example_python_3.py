import random
import time

def generate_random_numbers(count, start=1, end=100):
    return [random.randint(start, end) for _ in range(count)]

def bubble_sort(arr):
    n = len(arr)
    for i in range(n):
        for j in range(0, n-i-1):
            if arr[j] > arr[j+1]:
                arr[j], arr[j+1] = arr[j+1], arr[j]

def main():
    numbers = generate_random_numbers(50)
    print("Unsorted Numbers:", numbers)
    start_time = time.time()
    bubble_sort(numbers)
    end_time = time.time()
    print("Sorted Numbers:", numbers)
    print(f"Sorting took {end_time - start_time:.5f} seconds")

if __name__ == "__main__":
    main()

def fibonacci(n):
    if n <= 0:
        return []
    elif n == 1:
        return [0]
    elif n == 2:
        return [0, 1]
    fib_series = [0, 1]
    for i in range(2, n):
        fib_series.append(fib_series[-1] + fib_series[-2])
    return fib_series

def print_fibonacci():
    n = 10
    print(f"First {n} Fibonacci numbers: {fibonacci(n)}")

print_fibonacci()

def is_prime(n):
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

def generate_primes(limit):
    primes = []
    num = 2
    while len(primes) < limit:
        if is_prime(num):
            primes.append(num)
        num += 1
    return primes

def print_primes():
    limit = 10
    print(f"First {limit} prime numbers: {generate_primes(limit)}")

print_primes()

def factorial(n):
    if n == 0 or n == 1:
        return 1
    return n * factorial(n - 1)

def print_factorials():
    for i in range(10):
        print(f"Factorial of {i} is {factorial(i)}")

print_factorials()

def countdown(n):
    while n > 0:
        print(n)
        time.sleep(0.5)
        n -= 1
    print("Time's up!")

def run_countdown():
    countdown(5)

run_countdown()

