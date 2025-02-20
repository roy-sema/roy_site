import random
import datetime

def generate_random_numbers(count, start=1, end=100):
    """Generate a list of random numbers."""
    return [random.randint(start, end) for _ in range(count)]

class Person:
    """A simple Person class."""
    def __init__(self, name, age):
        self.name = name
        self.age = age

    def greet(self):
        return f"Hello, my name is {self.name} and I am {self.age} years old."

def write_to_file(filename, data):
    """Write data to a file."""
    with open(filename, "w") as file:
        file.write(data)

def read_from_file(filename):
    """Read data from a file."""
    with open(filename, "r") as file:
        return file.read()

def factorial(n):
    """Calculate factorial recursively."""
    return 1 if n == 0 else n * factorial(n - 1)

def fibonacci(n):
    """Generate Fibonacci sequence up to n elements."""
    sequence = [0, 1]
    for _ in range(n - 2):
        sequence.append(sequence[-1] + sequence[-2])
    return sequence

def current_datetime():
    """Return the current date and time."""
    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")

def check_prime(n):
    """Check if a number is prime."""
    if n < 2:
        return False
    for i in range(2, int(n ** 0.5) + 1):
        if n % i == 0:
            return False
    return True

def count_vowels(text):
    """Count vowels in a given string."""
    return sum(1 for char in text.lower() if char in "aeiou")

def main():
    print("Generating 10 random numbers:", generate_random_numbers(10))
    
    john = Person("John", 30)
    print(john.greet())
    
    print("Factorial of 5:", factorial(5))
    print("Fibonacci sequence (10 terms):", fibonacci(10))
    
    print("Checking primes between 1 and 20:")
    for num in range(1, 21):
        if check_prime(num):
            print(num, end=" ")
    print()
    
    sample_text = "Hello, how many vowels are in this sentence?"
    print(f"Vowel count: {count_vowels(sample_text)}")
    
    filename = "example.txt"
    write_to_file(filename, "This is an example file.")
    print("File contents:", read_from_file(filename))
    
    print("Current Date & Time:", current_datetime())
    
    print("Done!")

if __name__ == "__main__":
    main()
    
